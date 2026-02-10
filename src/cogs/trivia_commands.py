"""Trivia game commands with thread-based natural conversation."""

import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
import logging
import asyncio
from typing import Optional

from ..utils.game_session import GameSessionManager
from ..utils.trivia_ai import generate_question, validate_answer_complete
from ..utils.trivia_config import (
    DIFFICULTY_DESCRIPTIONS,
    GAME_MODE_DESCRIPTIONS,
    DEFAULT_QUESTIONS_PER_GAME,
    MAX_QUESTIONS_PER_GAME,
    NEXT_QUESTION_DELAY_SECONDS,
    QUESTION_TIMEOUT_SECONDS,
    COMPETITIVE_ANSWER_WINDOW_SECONDS,
    LEADERBOARD_PAGE_SIZE,
    get_rank_emoji,
    ACHIEVEMENTS
)

logger = logging.getLogger(__name__)


class TriviaCommands(commands.Cog):
    """Trivia game commands with thread-based interaction."""

    def __init__(self, bot):
        self.bot = bot
        self.game_manager = GameSessionManager()
        logger.info("TriviaCommands cog initialized")

    # Create trivia command group
    trivia = SlashCommandGroup(
        "trivia",
        "AI-powered trivia games with leaderboards and achievements"
    )

    @trivia.command(
        name="start",
        description="Start a new trivia game in a thread"
    )
    async def trivia_start(
        self,
        ctx: discord.ApplicationContext,
        mode: Option(
            str,
            description="Game mode",
            choices=["solo", "competitive"],
            required=True
        ),
        category: Option(
            str,
            description="Any topic you want (e.g., 'science', '80s movies', 'pokemon')",
            required=False,
            default=None
        ),
        difficulty: Option(
            str,
            description="Question difficulty",
            choices=["easy", "medium", "hard"],
            required=False,
            default="medium"
        ),
        questions: Option(
            int,
            description=f"Number of questions (1-{MAX_QUESTIONS_PER_GAME})",
            required=False,
            default=DEFAULT_QUESTIONS_PER_GAME,
            min_value=1,
            max_value=MAX_QUESTIONS_PER_GAME
        )
    ):
        """Start a new trivia game in a dedicated thread."""
        await ctx.defer()

        try:
            # Validate channel type
            if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
                await ctx.respond("❌ Trivia games can only be started in text channels or threads.", ephemeral=True)
                return

            # Get parent channel if in thread
            if isinstance(ctx.channel, discord.Thread):
                parent_channel = ctx.channel.parent
            else:
                parent_channel = ctx.channel

            # Create thread name
            category_text = category if category else "General Knowledge"
            mode_emoji = "🎯" if mode == "solo" else "⚔️"
            thread_name = f"{mode_emoji} {category_text} Trivia - {difficulty.capitalize()}"

            # Create the thread
            thread = await parent_channel.create_thread(
                name=thread_name[:100],  # Discord 100 char limit
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60  # Archive after 1 hour of inactivity
            )

            # Create database session
            state_manager = self.bot.state_manager
            session_id = state_manager.create_trivia_session(
                thread_id=str(thread.id),
                channel_id=str(parent_channel.id),
                user_id=str(ctx.author.id) if mode == "solo" else None,
                game_mode=mode,
                category=category,
                difficulty=difficulty,
                questions_total=questions
            )

            # Create in-memory game session
            game = self.game_manager.create_session(
                session_id=session_id,
                thread_id=str(thread.id),
                channel_id=str(parent_channel.id),
                game_mode=mode,
                category=category,
                difficulty=difficulty,
                questions_total=questions,
                host_user_id=str(ctx.author.id) if mode == "solo" else None
            )

            # Add host as player for solo mode
            if mode == "solo":
                game.add_player(str(ctx.author.id), ctx.author.display_name)

            # Send initial message to thread
            mode_desc = GAME_MODE_DESCRIPTIONS.get(mode, mode)
            difficulty_desc = DIFFICULTY_DESCRIPTIONS.get(difficulty, difficulty)

            intro_embed = discord.Embed(
                title=f"{mode_emoji} Trivia Game Started!",
                description=f"**Category:** {category_text}\n**{difficulty_desc}**\n**Mode:** {mode_desc}\n**Questions:** {questions}",
                color=discord.Color.blue()
            )
            intro_embed.add_field(
                name="How to Play",
                value="Just type your answer in this thread! You can use:\n• Option letters (A, B, C, D)\n• Full text answers\n• The bot will recognize both!",
                inline=False
            )

            if mode == "competitive":
                intro_embed.add_field(
                    name="Competitive Rules",
                    value="⚡ First correct answer wins each round!\n🏆 Earn points based on speed and streaks",
                    inline=False
                )

            await thread.send(embed=intro_embed)

            # Generate and post first question
            await self._post_next_question(thread, game)

            # Respond to the command
            await ctx.respond(f"✅ Trivia game started! Join the game in {thread.mention}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error starting trivia game: {e}", exc_info=True)
            await ctx.respond(f"❌ Failed to start trivia game: {str(e)}", ephemeral=True)

    @trivia.command(
        name="stop",
        description="End the current trivia game in this thread"
    )
    async def trivia_stop(self, ctx: discord.ApplicationContext):
        """Stop the current trivia game."""
        await ctx.defer()

        try:
            # Check if in a trivia thread
            thread_id = str(ctx.channel.id)
            game = self.game_manager.get_session(thread_id)

            if not game:
                await ctx.respond("❌ There's no active trivia game in this thread.", ephemeral=True)
                return

            # Check if user is authorized (host for solo, anyone for competitive)
            if game.game_mode == "solo" and str(ctx.author.id) != game.host_user_id:
                await ctx.respond("❌ Only the game host can stop a solo game.", ephemeral=True)
                return

            # End the game
            await self._end_game(ctx.channel, game, reason="Game stopped by user")
            await ctx.respond("✅ Game stopped.", ephemeral=True)

        except discord.NotFound:
            logger.debug("Thread was deleted, cleaning up session")
            await ctx.respond("✅ Game ended (thread was deleted).", ephemeral=True)
        except Exception as e:
            logger.error(f"Error stopping trivia game: {e}", exc_info=True)
            try:
                await ctx.respond(f"❌ Failed to stop game: {str(e)}", ephemeral=True)
            except discord.NotFound:
                logger.debug("Could not respond, interaction expired")

    @trivia.command(
        name="stats",
        description="View trivia statistics for yourself or another user"
    )
    async def trivia_stats(
        self,
        ctx: discord.ApplicationContext,
        user: Option(
            discord.Member,
            description="User to view stats for (default: yourself)",
            required=False
        )
    ):
        """Display trivia statistics."""
        await ctx.defer()

        try:
            target_user = user if user else ctx.author
            state_manager = self.bot.state_manager

            # Get user stats from database
            stats = state_manager.get_trivia_user_stats(
                user_id=str(target_user.id),
                server_id=str(ctx.guild.id)
            )

            if not stats:
                await ctx.respond(
                    f"📊 {target_user.display_name} hasn't played any trivia games yet!",
                    ephemeral=True
                )
                return

            # Calculate accuracy
            accuracy = 0.0
            if stats['total_questions'] > 0:
                accuracy = (stats['total_correct'] / stats['total_questions']) * 100

            # Create stats embed
            embed = discord.Embed(
                title=f"📊 Trivia Stats - {target_user.display_name}",
                color=discord.Color.green()
            )

            # Main stats
            embed.add_field(
                name="Games Played",
                value=f"🎮 {stats['total_games']}",
                inline=True
            )
            embed.add_field(
                name="Total Points",
                value=f"💰 {stats['total_points']:,}",
                inline=True
            )
            embed.add_field(
                name="Accuracy",
                value=f"🎯 {accuracy:.1f}%",
                inline=True
            )

            # Detailed stats
            embed.add_field(
                name="Questions",
                value=f"Answered: {stats['total_questions']}\nCorrect: {stats['total_correct']}",
                inline=True
            )
            embed.add_field(
                name="Streaks",
                value=f"Current: {stats['current_streak']}\nBest: {stats['best_streak']}",
                inline=True
            )
            embed.add_field(
                name="Avg Response Time",
                value=f"⏱️ {stats['average_response_time']:.1f}s",
                inline=True
            )

            # Get achievements
            achievements = state_manager.get_trivia_user_achievements(
                user_id=str(target_user.id),
                server_id=str(ctx.guild.id)
            )

            if achievements:
                achievement_text = "\n".join([
                    f"{ach['achievement_name']}" for ach in achievements[:5]
                ])
                if len(achievements) > 5:
                    achievement_text += f"\n... and {len(achievements) - 5} more"

                embed.add_field(
                    name=f"Achievements ({len(achievements)})",
                    value=achievement_text,
                    inline=False
                )

            embed.set_thumbnail(url=target_user.display_avatar.url)

            await ctx.respond(embed=embed)

        except Exception as e:
            logger.error(f"Error displaying stats: {e}", exc_info=True)
            await ctx.respond(f"❌ Failed to retrieve stats: {str(e)}", ephemeral=True)

    @trivia.command(
        name="leaderboard",
        description="View the server trivia leaderboard"
    )
    async def trivia_leaderboard(
        self,
        ctx: discord.ApplicationContext,
        timeframe: Option(
            str,
            description="Leaderboard timeframe",
            choices=["all_time"],  # TODO: Add daily, weekly, monthly when implemented
            required=False,
            default="all_time"
        )
    ):
        """Display the trivia leaderboard."""
        await ctx.defer()

        try:
            state_manager = self.bot.state_manager

            # Get leaderboard data
            leaderboard = state_manager.get_trivia_leaderboard(
                server_id=str(ctx.guild.id),
                timeframe=timeframe,
                limit=LEADERBOARD_PAGE_SIZE
            )

            if not leaderboard:
                await ctx.respond("📊 No trivia games have been played yet! Be the first to start one with `/trivia start`")
                return

            # Create leaderboard embed
            embed = discord.Embed(
                title=f"🏆 Trivia Leaderboard - {timeframe.replace('_', ' ').title()}",
                color=discord.Color.gold()
            )

            # Build leaderboard text
            leaderboard_text = []
            for rank, entry in enumerate(leaderboard, 1):
                # Try to get user
                user = ctx.guild.get_member(int(entry['user_id']))
                username = user.display_name if user else f"User {entry['user_id'][:8]}"

                # Calculate accuracy
                accuracy = 0.0
                if entry['total_questions'] > 0:
                    accuracy = (entry['total_correct'] / entry['total_questions']) * 100

                rank_emoji = get_rank_emoji(rank)
                leaderboard_text.append(
                    f"{rank_emoji} **{username}**\n"
                    f"   💰 {entry['total_points']:,} pts | "
                    f"🎯 {accuracy:.0f}% | "
                    f"🔥 {entry['best_streak']} streak"
                )

            embed.description = "\n\n".join(leaderboard_text)

            # Add footer with total games
            total_games = sum(entry['total_games'] for entry in leaderboard)
            embed.set_footer(text=f"Total games played: {total_games}")

            await ctx.respond(embed=embed)

        except Exception as e:
            logger.error(f"Error displaying leaderboard: {e}", exc_info=True)
            await ctx.respond(f"❌ Failed to retrieve leaderboard: {str(e)}", ephemeral=True)

    @trivia.command(
        name="achievements",
        description="View your trivia achievements"
    )
    async def trivia_achievements(self, ctx: discord.ApplicationContext):
        """Display user achievements."""
        await ctx.defer()

        try:
            state_manager = self.bot.state_manager

            # Get achievements
            achievements = state_manager.get_trivia_user_achievements(
                user_id=str(ctx.author.id),
                server_id=str(ctx.guild.id)
            )

            # Create embed
            embed = discord.Embed(
                title=f"🏆 Achievements - {ctx.author.display_name}",
                color=discord.Color.purple()
            )

            if not achievements:
                embed.description = "You haven't earned any achievements yet! Play some trivia games to unlock them."
            else:
                # Group achievements
                achievement_list = []
                for ach in achievements:
                    # Get full achievement details
                    ach_details = ACHIEVEMENTS.get(ach['achievement_type'])
                    if ach_details:
                        achievement_list.append(
                            f"{ach['achievement_name']}\n"
                            f"*{ach_details['description']}*"
                        )
                    else:
                        achievement_list.append(ach['achievement_name'])

                embed.description = "\n\n".join(achievement_list)

            # Show progress
            total_achievements = len(ACHIEVEMENTS)
            earned_count = len(achievements)
            embed.set_footer(text=f"{earned_count}/{total_achievements} achievements unlocked")

            await ctx.respond(embed=embed)

        except Exception as e:
            logger.error(f"Error displaying achievements: {e}", exc_info=True)
            await ctx.respond(f"❌ Failed to retrieve achievements: {str(e)}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for answers in trivia threads."""
        # Ignore bot messages
        if message.author.bot:
            return

        # Check if message is in an active trivia thread
        thread_id = str(message.channel.id)
        game = self.game_manager.get_session(thread_id)

        if not game or not game.is_waiting_for_answer:
            return

        # Process the answer
        try:
            user_answer = message.content.strip()

            # Validate answer
            state_manager = self.bot.state_manager
            ai_client = self.bot.openrouter_client  # Use OpenRouter for validation

            is_correct, match_type, ai_reason = await validate_answer_complete(
                user_answer=user_answer,
                correct_answer=game.current_correct_answer,
                options=game.current_options,
                question=game.current_question,
                ai_client=ai_client,
                channel_id=game.channel_id,
                state_manager=state_manager
            )

            # Process answer in game
            should_count, points_earned, winner_status = game.process_answer(
                user_id=str(message.author.id),
                username=message.author.display_name,
                is_correct=is_correct
            )

            if not should_count:
                # Duplicate answer or not waiting
                if winner_status == 'duplicate':
                    await message.add_reaction("⏭️")  # Skip emoji
                return

            # Send feedback
            if is_correct:
                # Get player state
                player = game.players[str(message.author.id)]

                # Build response based on winner status
                if game.game_mode == "competitive" and winner_status == "first_correct":
                    response = f"✅ **{message.author.mention} wins this round!**\n"
                    response += f"💰 +{points_earned} points"
                elif game.game_mode == "competitive" and winner_status == "also_correct":
                    response = f"✅ Correct! +{points_earned} points (partial credit)"
                else:
                    response = f"✅ Correct! +{points_earned} points"

                # Add streak info
                if player.current_streak >= 3:
                    response += f"\n🔥 Streak: {player.current_streak}"

                # Add AI reason if fuzzy match
                if match_type == 'ai_fuzzy' and ai_reason:
                    response += f"\n💡 {ai_reason}"

                await message.reply(response, mention_author=False)
                await message.add_reaction("✅")

            else:
                # Wrong answer
                if game.game_mode == "solo":
                    # Solo: show correct answer since we advance immediately
                    response = f"❌ Not quite! The correct answer was: **{game.current_correct_answer}**"
                else:
                    # Competitive: don't reveal answer, others may still try
                    response = f"❌ Not quite!"

                # Add AI reason if available
                if ai_reason and match_type == 'ai_rejected':
                    response += f"\n💡 {ai_reason}"

                await message.reply(response, mention_author=False)
                await message.add_reaction("❌")

            # Question advancement logic
            if game.game_mode == "solo":
                # Solo: complete immediately on any answer
                game.cancel_timers()
                game.complete_question()

                state_manager.update_trivia_questions_answered(thread_id)

                if game.is_game_complete():
                    await self._end_game(message.channel, game, reason="All questions answered")
                else:
                    await asyncio.sleep(NEXT_QUESTION_DELAY_SECONDS)
                    await self._post_next_question(message.channel, game)

            elif game.game_mode == "competitive" and winner_status == "first_correct":
                # First correct answer in competitive: cancel timeout, start answer window
                if game._question_timeout_task and not game._question_timeout_task.done():
                    game._question_timeout_task.cancel()
                    game._question_timeout_task = None

                game._answer_window_task = asyncio.create_task(
                    self._answer_window_handler(message.channel, game)
                )

                await message.channel.send(
                    f"⏳ Others have **{COMPETITIVE_ANSWER_WINDOW_SECONDS} seconds** to answer for partial credit!"
                )

            elif game.game_mode == "competitive" and winner_status == "also_correct":
                # Check if all known players have answered — close window early
                if len(game.answered_current_question) >= len(game.players):
                    game.cancel_timers()
                    game.complete_question()

                    state_manager.update_trivia_questions_answered(thread_id)

                    if game.is_game_complete():
                        await self._end_game(message.channel, game, reason="All questions answered")
                    else:
                        await asyncio.sleep(NEXT_QUESTION_DELAY_SECONDS)
                        await self._post_next_question(message.channel, game)
            # Competitive + incorrect: do nothing, let timeout or window handle advancement

        except Exception as e:
            logger.error(f"Error processing trivia answer: {e}", exc_info=True)
            await message.add_reaction("⚠️")

    async def _question_timeout_handler(self, channel: discord.TextChannel, game):
        """Handle question timeout when no correct answer arrives in time."""
        try:
            await asyncio.sleep(QUESTION_TIMEOUT_SECONDS)

            if not game.is_waiting_for_answer or not game.is_active:
                return

            # Time's up
            game.cancel_timers()
            game.complete_question()

            state_manager = self.bot.state_manager
            state_manager.update_trivia_questions_answered(game.thread_id)

            timeout_embed = discord.Embed(
                title="⏰ Time's Up!",
                description=f"Nobody answered correctly in time.\n\n**The correct answer was:** {game.current_correct_answer}",
                color=discord.Color.orange()
            )
            await channel.send(embed=timeout_embed)

            if game.is_game_complete():
                await self._end_game(channel, game, reason="All questions answered")
            else:
                await asyncio.sleep(NEXT_QUESTION_DELAY_SECONDS)
                await self._post_next_question(channel, game)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in question timeout handler: {e}", exc_info=True)

    async def _answer_window_handler(self, channel: discord.TextChannel, game):
        """Handle the competitive answer window after the first correct answer."""
        try:
            await asyncio.sleep(COMPETITIVE_ANSWER_WINDOW_SECONDS)

            if not game.is_waiting_for_answer or not game.is_active:
                return

            # Window expired — complete the question and advance
            game.cancel_timers()
            game.complete_question()

            state_manager = self.bot.state_manager
            state_manager.update_trivia_questions_answered(game.thread_id)

            if game.is_game_complete():
                await self._end_game(channel, game, reason="All questions answered")
            else:
                await asyncio.sleep(NEXT_QUESTION_DELAY_SECONDS)
                await self._post_next_question(channel, game)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in answer window handler: {e}", exc_info=True)

    async def _check_and_award_achievements(self, channel, game, player_standing, state_manager):
        """Check and award achievements for a single player. Returns list of achievement text strings."""
        leaderboard_stats = state_manager.get_trivia_user_stats(
            user_id=player_standing['user_id'],
            server_id=str(channel.guild.id)
        )
        newly_earned = game.check_achievements_for_player(
            player_standing['user_id'],
            leaderboard_stats
        )

        achievement_text = []
        if newly_earned:
            for ach_id in newly_earned:
                if not state_manager.has_trivia_achievement(
                    user_id=player_standing['user_id'],
                    server_id=str(channel.guild.id),
                    achievement_type=ach_id
                ):
                    ach = ACHIEVEMENTS[ach_id]
                    state_manager.add_trivia_achievement(
                        user_id=player_standing['user_id'],
                        server_id=str(channel.guild.id),
                        achievement_type=ach_id,
                        achievement_name=ach['name']
                    )
                    achievement_text.append(f"{ach['name']}\n*{ach['description']}*")

        return achievement_text

    async def _post_next_question(self, channel: discord.TextChannel, game):
        """Generate and post the next question."""
        try:
            # Generate question
            state_manager = self.bot.state_manager
            ai_client = self.bot.openrouter_client

            question_data = await generate_question(
                category=game.category or "general knowledge",
                difficulty=game.difficulty,
                ai_client=ai_client,
                channel_id=game.channel_id,
                state_manager=state_manager,
                asked_questions=game.asked_questions
            )

            if not question_data:
                await channel.send("❌ Failed to generate question. Ending game.")
                await self._end_game(channel, game, reason="Question generation failed")
                return

            # Post question to game
            game.post_question(question_data)

            # Format options with letters
            option_letters = ['A', 'B', 'C', 'D']
            options_text = "\n".join([
                f"**{option_letters[i]})** {option}"
                for i, option in enumerate(question_data['options'])
            ])

            # Create embed
            embed = discord.Embed(
                title=f"Question {game.questions_answered + 1}/{game.questions_total}",
                description=f"**{question_data['question']}**\n\n{options_text}",
                color=discord.Color.blue()
            )

            # Add category and difficulty
            category_text = game.category if game.category else "General Knowledge"
            embed.set_footer(text=f"{category_text} • {game.difficulty.capitalize()}")

            await channel.send(embed=embed)

            # Start question timeout timer
            game.cancel_timers()
            game._question_timeout_task = asyncio.create_task(
                self._question_timeout_handler(channel, game)
            )

        except Exception as e:
            logger.error(f"Error posting question: {e}", exc_info=True)
            await channel.send("❌ Error posting question. Ending game.")
            await self._end_game(channel, game, reason="Error posting question")

    async def _end_game(self, channel: discord.TextChannel, game, reason: str = "Game completed"):
        """End a trivia game and show final results."""
        try:
            # Cancel any active timers
            game.cancel_timers()

            state_manager = self.bot.state_manager

            # Get final standings
            standings = game.get_current_standings()

            # Create summary embed
            embed = discord.Embed(
                title="🎉 Game Complete!",
                description=f"**{reason}**",
                color=discord.Color.green()
            )

            # Add standings
            if standings:
                if game.game_mode == "solo":
                    # Solo mode - single player summary
                    player = standings[0]
                    embed.add_field(
                        name="📊 Your Results",
                        value=(
                            f"**Score:** {player['score']:,} points\n"
                            f"**Correct:** {player['correct']}/{player['total']} ({player['accuracy']:.1f}%)\n"
                            f"**Best Streak:** {player['best_streak']}\n"
                            f"**Avg Time:** {player['avg_time']:.1f}s"
                        ),
                        inline=False
                    )

                    # Update leaderboard for solo player
                    state_manager.update_trivia_leaderboard(
                        user_id=player['user_id'],
                        server_id=str(channel.guild.id),
                        questions_answered=player['total'],
                        correct_answers=player['correct'],
                        points_earned=player['score'],
                        current_streak=player['streak'],
                        response_time=player['avg_time']
                    )

                    # Check for achievements
                    achievement_text = await self._check_and_award_achievements(
                        channel, game, player, state_manager
                    )
                    if achievement_text:
                        embed.add_field(
                            name="🏆 New Achievements!",
                            value="\n\n".join(achievement_text),
                            inline=False
                        )

                else:
                    # Competitive mode - leaderboard
                    leaderboard_text = []
                    for rank, player in enumerate(standings, 1):
                        rank_emoji = get_rank_emoji(rank)
                        leaderboard_text.append(
                            f"{rank_emoji} **{player['username']}** - {player['score']:,} pts "
                            f"({player['correct']}/{player['total']})"
                        )

                        # Update leaderboard for each player
                        state_manager.update_trivia_leaderboard(
                            user_id=player['user_id'],
                            server_id=str(channel.guild.id),
                            questions_answered=player['total'],
                            correct_answers=player['correct'],
                            points_earned=player['score'],
                            current_streak=player['streak'],
                            response_time=player['avg_time']
                        )

                    embed.add_field(
                        name="🏆 Final Standings",
                        value="\n".join(leaderboard_text),
                        inline=False
                    )

                    # Check achievements for ALL competitive players
                    all_achievements = []
                    for player in standings:
                        player_achievements = await self._check_and_award_achievements(
                            channel, game, player, state_manager
                        )
                        if player_achievements:
                            user = channel.guild.get_member(int(player['user_id']))
                            username = user.display_name if user else player['username']
                            for ach_text in player_achievements:
                                all_achievements.append(f"**{username}**: {ach_text}")

                    if all_achievements:
                        embed.add_field(
                            name="🏆 New Achievements!",
                            value="\n\n".join(all_achievements[:10]),
                            inline=False
                        )

            await channel.send(embed=embed)

            # End database session
            state_manager.end_trivia_session(str(channel.id))

            # End in-memory session
            self.game_manager.end_session(str(channel.id))

            # Archive thread after a delay
            if isinstance(channel, discord.Thread):
                try:
                    await asyncio.sleep(30)  # Wait 30 seconds before archiving
                    await channel.edit(archived=True)
                except discord.NotFound:
                    logger.debug(f"Thread {channel.id} was already deleted, skipping archive")
                except Exception as e:
                    logger.error(f"Error archiving thread {channel.id}: {e}")

        except discord.NotFound:
            # Channel was deleted, silently clean up
            logger.debug(f"Channel no longer exists, cleaning up game session")
            try:
                state_manager.end_trivia_session(str(channel.id))
                self.game_manager.end_session(str(channel.id))
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup: {cleanup_error}")
        except Exception as e:
            logger.error(f"Error ending game: {e}", exc_info=True)
            try:
                await channel.send(f"⚠️ Error ending game: {str(e)}")
            except discord.NotFound:
                logger.debug(f"Could not send error message, channel was deleted")


def setup(bot):
    """Setup function called by Discord.py when loading the cog."""
    bot.add_cog(TriviaCommands(bot))
    logger.info("TriviaCommands cog loaded")

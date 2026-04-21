import discord
from discord import app_commands
from discord.ext import commands
import os

# -----------------------------------------------
# BOT設定
# -----------------------------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ ログイン成功: {bot.user} (ID: {bot.user.id})")
    print("スラッシュコマンドを同期しました")


# -----------------------------------------------
# /move コマンド
# 使い方: /move channel:#チャンネル category:カテゴリー名
# -----------------------------------------------
@tree.command(name="move", description="このチャンネルを指定したカテゴリーに移動します")
@app_commands.describe(
    category="移動先のカテゴリー名"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def move_channel(
    interaction: discord.Interaction,
    category: str
):
    guild = interaction.guild
    channel = interaction.channel

    # カテゴリー名で検索（大文字小文字を区別しない）
    target_category = discord.utils.find(
        lambda c: c.name.lower() == category.lower(),
        guild.categories
    )

    if target_category is None:
        # 見つからない場合、候補を提示
        all_categories = [c.name for c in guild.categories]
        candidates = "\n".join(f"・{name}" for name in all_categories) if all_categories else "（カテゴリーなし）"
        await interaction.response.send_message(
            f"❌ カテゴリー「{category}」が見つかりませんでした。\n\n"
            f"**利用可能なカテゴリー一覧:**\n{candidates}",
            ephemeral=True
        )
        return

    # 移動前のカテゴリーを記録
    old_category = channel.category.name if channel.category else "（なし）"

    # チャンネルをカテゴリーに移動
    try:
        await channel.edit(category=target_category)
        await interaction.response.send_message(
            f"✅ **{channel.name}** を移動しました\n"
            f"　`{old_category}` → `{target_category.name}`",
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ BOTに「チャンネルの管理」権限がありません。",
            ephemeral=True
        )
    except discord.HTTPException as e:
        await interaction.response.send_message(
            f"❌ エラーが発生しました: {e}",
            ephemeral=True
        )


# カテゴリー名のオートコンプリート
@move_channel.autocomplete("category")
async def category_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    categories = interaction.guild.categories
    return [
        app_commands.Choice(name=c.name, value=c.name)
        for c in categories
        if current.lower() in c.name.lower()
    ][:25]  # Discord の上限は25件


# -----------------------------------------------
# /archive コマンド
# 実行したチャンネルを「アーカイブ20XX」カテゴリーに移動
# カテゴリーが存在しない場合は自動作成
# -----------------------------------------------
@tree.command(name="archive", description="このチャンネルをアーカイブカテゴリーに移動します")
@app_commands.checks.has_permissions(manage_channels=True)
async def archive_channel(interaction: discord.Interaction):
    import datetime
    guild = interaction.guild
    channel = interaction.channel
    current_category = channel.category

    # 移動先カテゴリー名を決定
    # 現在のカテゴリーが「ボドゲ」ならボドゲ会アーカイブ、それ以外は年別アーカイブ
    if current_category and current_category.name == "ボドゲ":
        category_name = "アーカイブ_ボドゲ会"
    else:
        year = datetime.datetime.now().year
        category_name = f"アーカイブ_{year}"

    # カテゴリーを検索
    target_category = discord.utils.find(
        lambda c: c.name == category_name,
        guild.categories
    )

    # 存在しなければ自動作成
    if target_category is None:
        try:
            target_category = await guild.create_category(category_name)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ カテゴリーを作成する権限がありません。",
                ephemeral=True
            )
            return

    old_category = current_category.name if current_category else "（なし）"

    try:
        await channel.edit(category=target_category)
        await interaction.response.send_message(
            f"📦 **{channel.name}** をアーカイブしました\n"
            f"　`{old_category}` → `{category_name}`"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ BOTに「チャンネルの管理」権限がありません。",
            ephemeral=True
        )
    except discord.HTTPException as e:
        await interaction.response.send_message(
            f"❌ エラーが発生しました: {e}",
            ephemeral=True
        )


@archive_channel.error
async def archive_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ このコマンドを使うには **チャンネルの管理** 権限が必要です。",
            ephemeral=True
        )


# -----------------------------------------------
# /trpg_start コマンド
# 「卓募集」チャンネルからシナリオ名で募集投稿を探し
# リアクションしたメンバー＋投稿者でプライベートチャンネルを作成
# -----------------------------------------------
@tree.command(name="trpg_start", description="TRPGのプライベートチャンネルを作成します")
@app_commands.describe(
    scenario="シナリオ名（卓募集チャンネルの「シナリオ名：〇〇」と一致するもの）",
    category="作成先のカテゴリー名"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def trpg_start(
    interaction: discord.Interaction,
    scenario: str,
    category: str
):
    await interaction.response.defer()
    guild = interaction.guild

    # 「卓募集」チャンネルを探す
    recruit_channel = discord.utils.find(
        lambda c: c.name == "卓募集",
        guild.text_channels
    )
    if recruit_channel is None:
        await interaction.followup.send(
            "❌「卓募集」チャンネルが見つかりませんでした。",
            ephemeral=True
        )
        return

    # 卓募集チャンネルからシナリオ名が含まれる投稿を探す
    recruit_message = None
    async for message in recruit_channel.history(limit=100):
        if f"シナリオ名：{scenario}" in message.content or f"シナリオ名:{scenario}" in message.content:
            recruit_message = message
            break

    if recruit_message is None:
        await interaction.followup.send(
            f"❌「シナリオ名：{scenario}」の募集投稿が見つかりませんでした。\n"
            f"「卓募集」チャンネルの直近100件を検索しました。",
            ephemeral=True
        )
        return

    # メンバーを収集（投稿者＋リアクションしたユーザー）
    members = {recruit_message.author}
    for reaction in recruit_message.reactions:
        async for user in reaction.users():
            if not user.bot:
                members.add(user)

    # サーバーオーナーを自動追加
    members.add(guild.owner)

    # カテゴリーを検索
    target_category = discord.utils.find(
        lambda c: c.name.lower() == category.lower(),
        guild.categories
    )
    if target_category is None:
        try:
            target_category = await guild.create_category(category)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ カテゴリーを作成する権限がありません。",
                ephemeral=True
            )
            return

    # プライベートチャンネルの権限設定
    # デフォルト：全員閲覧不可
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    # メンバーに閲覧・書き込み権限を付与
    for member in members:
        overwrites[member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True
        )

    # チャンネル名を作成（スペースはハイフンに変換）
    channel_name = scenario.replace(" ", "-").replace("　", "-")

    # プライベートチャンネルを作成
    try:
        new_channel = await guild.create_text_channel(
            name=channel_name,
            category=target_category,
            overwrites=overwrites
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ BOTにチャンネルを作成する権限がありません。",
            ephemeral=True
        )
        return

    # メンバー一覧を表示
    member_mentions = " ".join(m.mention for m in members)
    await interaction.followup.send(
        f"✅ プライベートチャンネルを作成しました\n"
        f"　チャンネル：{new_channel.mention}\n"
        f"　メンバー：{member_mentions}"
    )
    # 作成したチャンネルにも通知
    await new_channel.send(
        f"🎲 **{scenario}** のチャンネルを作成しました！\n"
        f"メンバー：{member_mentions}"
    )


@trpg_start.autocomplete("category")
async def trpg_category_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=c.name, value=c.name)
        for c in interaction.guild.categories
        if current.lower() in c.name.lower()
    ][:25]


@trpg_start.error
async def trpg_start_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ このコマンドを使うには **チャンネルの管理** 権限が必要です。",
            ephemeral=True
        )


# 権限エラーのハンドリング
@move_channel.error
async def move_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ このコマンドを使うには **チャンネルの管理** 権限が必要です。",
            ephemeral=True
        )


# -----------------------------------------------
# 起動
# -----------------------------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("環境変数 DISCORD_TOKEN が設定されていません")

bot.run(TOKEN)

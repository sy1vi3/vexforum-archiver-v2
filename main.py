"""Import stuff"""
import requests
import json
import re
import datetime
import time
import asyncio
import dateutil.parser as dp
from bs4 import BeautifulSoup
from peewee import *
import discord
from discord.ext.commands import Bot
import tokens
import constants

intents = discord.Intents.default()
client = Bot(command_prefix = "!", intents=intents)
new_posts = None
edited_posts = None
deleted_posts = None
system_posts = None
staff_posts = None




"""Database Setup"""
db = PostgresqlDatabase('vexforum', user=tokens.db_user, password=tokens.db_password, host=tokens.db_host, port=tokens.db_port)
class BaseModel(Model):
    class Meta:
        database = db
class Posts(BaseModel):
    guid = IntegerField()
    author = TextField()
    author_name = TextField(null=True)
    author_id = IntegerField()
    author_pfp = TextField(null=True)
    timestamp = TimestampField(null=True)
    topic_id = IntegerField()
    post_number = IntegerField()
    reply_to_post_number = IntegerField(null=True)
    raw_content = TextField()
    cooked_content = TextField(null=True)
    is_staff = BooleanField(null=True)
    post_type = IntegerField()
    is_system = BooleanField(null=True)
    edit_number = IntegerField(null=True)
    is_removed = BooleanField(null=True)
    deleted_by_user = BooleanField(null=True)
    topic_title = TextField(null=True)
    url = TextField(null=True)

def timestamp_log():
    time_now = datetime.datetime.now()
    return f"{time_now.month}/{time_now.day}/{time_now.year} {time_now.hour}:{time_now.minute}"

async def get_page():
    r = requests.get('https://www.vexforum.com/posts.json')
    if r.status_code == 429:
        requests.post(tokens.logs_webhook, json={"content": f"{timestamp_log()} - 429 Too Many Requests [Fetching JSON Feed]"})
        time.sleep(60)
        feed = await get_page()
        return feed
    elif r.status_code != 200:
        requests.post(tokens.logs_webhook, json={"content": f"{timestamp_log()} - {r.status_code} [Fetching JSON Feed]: `{r.text}`"})
        time.sleep(60)
        feed = await get_page()
        return feed
    else:
        return json.loads(r.text)

async def scrape_feed(old_feed=None):
    global new_posts
    global edited_posts
    global deleted_posts
    global system_posts
    global staff_posts


    feed = await get_page()
    if feed == old_feed:
        return feed
    posts = feed['latest_posts']
    for post in posts:
        post_guid = post['id']
        post_author = post['username']
        post_author_name = post['name']
        post_author_id = post['user_id']
        post_author_pfp = f'https://vexforum.com/{re.sub(r"{size}", "80", post["avatar_template"])}'
        post_timestamp = round(dp.parse(post['updated_at']).timestamp())
        post_topic_id = post['topic_id']
        post_post_number = post['post_number']
        post_reply_to_post_number = post['reply_to_post_number']
        try:
            post_raw_content = post['raw']
        except KeyError:
            r = requests.get(f"https://www.vexforum.com/raw/{post_topic_id}/{post_post_number}")
            if r.status_code != 200:
                print("Error getting raw post")
                post_raw_content = post_cooked_content
            else:
                post_raw_content = r.text
        post_cooked_content = post['cooked']
        post_is_staff = True if post['moderator'] or post['admin'] or post['staff'] else False
        post_post_type = post['post_type']
        post_is_system = True if post_author_id == -1 else False
        post_edit_number = 0
        post_deleted_at = post['deleted_at']
        post_user_deleted = post['user_deleted']
        post_topic_title = post['topic_title']
        post_is_wiki = post['wiki']
        post_author_trust_level = post['trust_level']
        post_url = f'https://vexforum.com/t/{post_topic_id}/{post_post_number}'
        parsed_cooked = BeautifulSoup(post_cooked_content, 'html.parser')
        img_tags = parsed_cooked.find_all('img')
        links = parsed_cooked.find_all('a')
        urls = [img['src'] for img in img_tags]
        for index, url in enumerate(urls):
            if 'letter_avatar' in url or 'user_avatar' in url or 'emoji' in url:
                urls.remove(url)
                continue
            if re.match('^\/uploads', url):
                new_url = f'https://vexforum.com{url}'
                urls[index] = new_url
        post_timestamp_readable = str(datetime.datetime.utcfromtimestamp(post_timestamp) + datetime.timedelta(hours=-7)) + ' MST'
        query = Posts.select().where(Posts.guid == post_guid).order_by(Posts.edit_number.desc())
        exist_check = query.count()
        if exist_check == 0: # If the guid is unique
            if post_is_system is not True:
                new_post = Posts.create(guid=post_guid, author=post_author, author_name=post_author_name, author_id=post_author_id, author_pfp=post_author_pfp, timestamp=post_timestamp, topic_id=post_topic_id, post_number=post_post_number, reply_to_post_number=post_reply_to_post_number, raw_content=post_raw_content, cooked_content=post_cooked_content, is_staff=post_is_staff, post_type=post_post_type, is_system=post_is_system, edit_number=post_edit_number, topic_title=post_topic_title, url=post_url)
                embed=discord.Embed(title=post_topic_title, url=post_url, description=post_timestamp_readable, color=0x48d421)
                embed.set_thumbnail(url=post_author_pfp)
                embed.add_field(name=f"New post from {post_author}", value=post_raw_content[0:1024], inline=True)
                if len(urls) == 0: # If there are no imaqes
                    pass
                elif len(urls) == 1: # If there is one image
                    embed.set_image(url=urls[0])
                elif len(urls) >= 2: # 2 or more images
                    url_str = ''
                    for url in urls:
                        url_str += f'{url} \n'
                    embed.add_field(name=f"Images in the post", value=url_str[0:1024], inline=False)
                if post_is_staff:
                    await staff_posts.send(embed=embed)
                else:
                    await new_posts.send(embed=embed)
                await tokens.post_analysis(new_post, "", "")
            else:
                Posts.create(guid=post_guid, author=post_author, author_name=post_author_name, author_id=post_author_id, author_pfp=post_author_pfp, timestamp=post_timestamp, topic_id=post_topic_id, post_number=post_post_number, reply_to_post_number=post_reply_to_post_number, raw_content=post_raw_content, cooked_content=post_cooked_content, is_staff=post_is_staff, post_type=post_post_type, is_system=post_is_system, edit_number=post_edit_number, topic_title=post_topic_title, url=post_url)
                embed=discord.Embed(title=post_topic_title, url=post_url, description=post_timestamp_readable, color=0x878787)
                embed.set_thumbnail(url=post_author_pfp)
                embed.add_field(name="System Message", value=post_raw_content[0:1024], inline=True)
                await system_posts.send(embed=embed)
        else:
            if (post_deleted_at is not None or post_user_deleted) and query[0].raw_content != post_raw_content: # Deleted post
                post_edit_number = query[0].edit_number + 1
                if post_user_deleted:
                    Posts.create(guid=post_guid, author=post_author, author_name=post_author_name, author_id=post_author_id, author_pfp=post_author_pfp, timestamp=post_timestamp, topic_id=post_topic_id, post_number=post_post_number, reply_to_post_number=post_reply_to_post_number, raw_content=post_raw_content, cooked_content=post_cooked_content, is_staff=post_is_staff, post_type=post_post_type, is_system=post_is_system, edit_number=post_edit_number, is_removed=True, deleted_by_user=True, topic_title=post_topic_title, url=post_url)
                    embed=discord.Embed(title=post_topic_title, url=post_url, description=post_timestamp_readable, color=0xf50f0f)
                    embed.set_thumbnail(url=post_author_pfp)
                    embed.add_field(name=f"{post_author} deleted a post", value=query[0].raw_content[0:1024], inline=True)
                    old_parsed_cooked = BeautifulSoup(query[0].cooked_content, 'html.parser')
                    old_img_tags = old_parsed_cooked.find_all('img')
                    old_urls = [img['src'] for img in old_img_tags]
                    for index, url in enumerate(old_urls):
                        if 'letter_avatar' in url or 'user_avatar' in url or 'emoji' in url:
                            old_urls.remove(url)
                            continue
                        if re.match('^\/uploads', url):
                            new_url = f'https://vexforum.com{url}'
                            old_urls[index] = new_url
                    if len(old_urls) == 0: # If there are no imaqes
                        pass
                    elif len(old_urls) == 1: # If there is one image
                        embed.set_image(url=old_urls[0])
                    elif len(old_urls) >= 2: # 2 or more images
                        url_str = ''
                        for url in old_urls:
                            url_str += f'{url} \n'
                        embed.add_field(name=f"Images in the post", value=url_str[0:1024], inline=False)
                    await deleted_posts.send(embed=embed)
                else: # Removed Post
                    Posts.create(guid=post_guid, author=post_author, author_name=post_author_name, author_id=post_author_id, author_pfp=post_author_pfp, timestamp=post_timestamp, topic_id=post_topic_id, post_number=post_post_number, reply_to_post_number=post_reply_to_post_number, raw_content=post_raw_content, cooked_content=post_cooked_content, is_staff=post_is_staff, post_type=post_post_type, is_system=post_is_system, edit_number=post_edit_number, is_removed=True, deleted_by_user=False, topic_title=post_topic_title, url=post_url)
                    embed=discord.Embed(title=post_topic_title, url=post_url, description=post_timestamp_readable, color=0x9d1bda)
                    embed.set_thumbnail(url=post_author_pfp)
                    embed.add_field(name=f"{post_author}'s post was removed", value=query[0].raw_content[0:1024], inline=True)
                    await deleted_posts.send(embed=embed)
            elif query[0].raw_content != post_raw_content: # Edit Event
                post_edit_number = query[0].edit_number + 1
                Posts.create(guid=post_guid, author=post_author, author_name=post_author_name, author_id=post_author_id, author_pfp=post_author_pfp, timestamp=post_timestamp, topic_id=post_topic_id, post_number=post_post_number, reply_to_post_number=post_reply_to_post_number, raw_content=post_raw_content, cooked_content=post_cooked_content, is_staff=post_is_staff, post_type=post_post_type, is_system=post_is_system, edit_number=post_edit_number, topic_title=post_topic_title, url=post_url)
                if not post_is_wiki:
                    embed=discord.Embed(title=post_topic_title, url=post_url, description=post_timestamp, color=0xf5e60f)
                else:
                    embed=discord.Embed(title=post_topic_title, url=post_url, description=post_timestamp, color=0xfb8f13)
                embed.set_thumbnail(url=post_author_pfp)
                if not post_is_wiki:
                    embed.add_field(name=f"Edited post from {post_author}", value=post_raw_content[0:1024], inline=True)
                else:
                    embed.add_field(name=f"{post_author}'s wiki post was edited'", value=post_raw_content[0:1024], inline=True)
                if len(urls) == 0: # If there are no imaqes
                    pass
                elif len(urls) == 1: # If there is one image
                    embed.set_image(url=urls[0])
                elif len(urls) >= 2: # 2 or more images
                    url_str = ''
                    for url in urls:
                        url_str += f'{url} \n'
                    embed.add_field(name=f"Images in the new post", value=url_str[0:1024], inline=False)
                embed.add_field(name=f"Previous post content", value=query[0].raw_content[0:1024], inline=False)
                old_parsed_cooked = BeautifulSoup(query[0].cooked_content, 'html.parser')
                old_img_tags = old_parsed_cooked.find_all('img')
                old_urls = [img['src'] for img in old_img_tags]
                for index, url in enumerate(old_urls):
                    if 'letter_avatar' in url or 'user_avatar' in url or 'emoji' in url:
                        old_urls.remove(url)
                        continue
                    if re.match('^\/uploads', url):
                        new_url = f'https://vexforum.com{url}'
                        old_urls[index] = new_url
                if len(old_urls) == 0: # If there are no imaqes
                    pass
                elif len(old_urls) == 1: # If there is one image
                    embed.set_image(url=old_urls[0])
                elif len(old_urls) >= 2: # 2 or more images
                    url_str = ''
                    for url in old_urls:
                        url_str += f'{url} \n'
                    embed.add_field(name=f"Images in the old version of the post", value=url_str[0:1024], inline=False)
                await edited_posts.send(embed=embed)
    return feed

async def check_deletes(timeframe=86400):
    global new_posts
    global edited_posts
    global deleted_posts
    global system_posts
    global staff_posts
    removed_guids = set()
    while True:
        query = Posts.select().where(Posts.is_removed == None, (time.time() - Posts.timestamp) < timeframe).order_by(Posts.timestamp, Posts.edit_number.desc())
        for post in query:
            if post.guid in removed_guids:
                continue
            r = requests.get(f'https://www.vexforum.com/raw/{post.topic_id}/{post.post_number}')
            post_timestamp_readable = post.timestamp.strftime("%m/%d/%Y, %H:%M:%S")
            if r.status_code == 404: # Post removed/deleted
                removed_guids.add(post.guid)
                update_record = Posts.update(is_removed = True).where(Posts.guid == post.guid)
                update_record.execute()
                embed=discord.Embed(title=post.topic_title, url=post.url, description=post_timestamp_readable, color=0x9d1bda)
                embed.set_thumbnail(url=post.author_pfp)
                embed.add_field(name=f"{post.author}'s post was deleted or removed", value=post.raw_content[0:1024], inline=True)
                await deleted_posts.send(embed=embed)
            elif r.text == "(post deleted by author)":
                removed_guids.add(post.guid)
                update_record = Posts.update(is_removed = True).where(Posts.guid == post.guid)
                update_record.execute()
                embed=discord.Embed(title=post.topic_title, url=post.url, description=post_timestamp_readable, color=0xf50f0f)
                embed.set_thumbnail(url=post.author_pfp)
                embed.add_field(name=f"{post.author} deleted their post", value=post.raw_content[0:1024], inline=True)
                await deleted_posts.send(embed=embed)
            elif r.status_code == 403:
                pass
            await asyncio.sleep(45)
async def run_scraper_service():
    old_feed_page = None
    loop = asyncio.get_event_loop()
    loop.create_task(check_deletes())
    while True:
        try:
            old_feed_page = await scrape_feed(old_feed=old_feed_page)
            await asyncio.sleep(30)
        except Exception as e:
            print(e)

@client.event
async def on_ready():
    global new_posts
    global edited_posts
    global deleted_posts
    global system_posts
    global staff_posts
    print("ready")
    new_posts = client.get_channel(constants.new_posts)
    edited_posts = client.get_channel(constants.edited_posts)
    deleted_posts = client.get_channel(constants.deleted_posts)
    system_posts = client.get_channel(constants.system_posts)
    staff_posts = client.get_channel(constants.staff_posts)
    startup_log = client.get_channel(constants.startup_log)
    await startup_log.send("`Archiver is online`")
    await run_scraper_service()

@client.command()
async def ping(ctx):
    await ctx.reply("Pong!")

@client.command()
async def old(ctx, url):
    regex_url = re.search(r'\/\d+\/\d+', url)
    if regex_url:
        id = regex_url.group()
        topic_id = re.search('\/\d+\/', id).group()[1:-1]
        reply_id = re.search('\/\d+$', id).group()[1:]
        print(reply_id, topic_id)
        query = Posts.select().where(Posts.topic_id == topic_id, Posts.post_number == reply_id).order_by(Posts.edit_number)
        if len(query) == 0:
            await ctx.send("Sorry, I can't find this post in my records")
            return
        post_timestamp_readable = query[0].timestamp.strftime("%m/%d/%Y, %H:%M:%S")
        embed=discord.Embed(title=query[0].topic_title, url=query[0].url, description=post_timestamp_readable, color=0x23cfc3)
        embed.set_thumbnail(url=query[0].author_pfp)
        embed.add_field(name=f"{query[0].author}'s original post", value=query[0].raw_content[0:1024], inline=False)
        for index, post in enumerate(query, start=1):
            if index == 1:
                continue
            embed.add_field(name=f"Edit #{post.edit_number}", value=post.raw_content[0:1024], inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("Sorry, I couldn't understand that request. Make sure to include a link to the post you're trying to see the history of, or the post's `topic` and `reply` IDs such as `12345/67`.")

if __name__ == '__main__':
    db.connect()
    db.create_tables([Posts], safe=True)
    client.run(tokens.bot_token)

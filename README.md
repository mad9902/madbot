# Command discord bot
```
General commands:
mad help                   - displays all the available commands
mad clear / cl <amount>    - will delete the past messages with the amount specified

Image commands:
mad emoji <emoji>                  - will get the emoji
mad sticker <sticker               - will get the sticker
mad avatar <tag>                   - will get the avatar from the user

Music commands:
mad p or play <keywords>       - finds the song on youtube and plays 
                                 it in your current channel
mad q or queue                 - displays the current music queue
mad skip                       - skips the current song being played
mad setch <id channel>         - to set channel for music
mad leave or disconnect / dc
mad shuffle
mad loop current / queue


Polls & Voting:
mad poll <question>                    - create a yes/no poll

Giveaway:
mad giveaway <prize> <duration_seconds> - start a giveaway with prize and duration

Role Reaction:
mad rolemenu                        - create role selection menu with reactions

XP System:
mad level                           - check your current XP level
mad setrolelvl <level> <id role>
mad removerolelvl <level> <id role>

Auto Send:
Instagram or tiktok link

Info:
mad serverinfo
mad userinfo <tag>

```
`

# bot.py
Responsible for handling all the discord API stuff

# need to install the following libraries
pip install discord.py[voice]
pip install youtube_dl

## to install google_images_download (download the feature branch with the fix)
git clone https://github.com/Joeclinton1/google-images-download.git
cd google-images-download && python setup.py install
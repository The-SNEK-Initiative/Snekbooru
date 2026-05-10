<p align="center">
  <img src="graphics/logo.png" alt="Snekbooru Logo" width="512">
</p>

# IMPORTANT NOTICE
### This README is still maintained, however it is recommended
that you go to https://snekbooru.org/ for more information regarding this project. (Usually a few hours/days behind on updates however)

# Snekbooru
### Finally common sourced!
## Disclaimers
  - **THIS IS NOT A WRAPPER FOR THE PyPi PROJECT [Snakebooru](https://pypi.org/project/snakebooru)**
  - **THIS PROJECT IS COMMON SOURCE, FOR MORE INFORMATION AND INQUIERIES PLEASE CONTACT THE CREATOR AND DEVELOPER atroubledsnake**
  - **PROJECT VERSIONS 6.0.0 AND BELOW MAY CAUSE WINDOWS DEFENDER OR YOUR ANTIVIRUS TO BLOCK OUR APP DURING INSTALL OR RUNNING, THIS IS BECAUSE OF THE FACT WE DO NOT POSSES A CODE SIGNING LISCENCE AND OBFUSCATION TECHNIQUES USED TO KEEP THE SOURCE CODE SECURE**
  - **NOTE: IF YOU POSSES A VERSION FROM PRE 6.0.0 IF YOU INSTALL THE NEWEST VERSION YOU WILL HAVE TO MANUALLY REMOVE THE OLD INSTALLATION IN C:\Program Files (x86)\Snekbooru, SINCE THE NEW INSTALLER INSTALLS TO C:\Program Files\Snekbooru AND YOU WILL END UP WITH TWO INSTALLATIONS IF YOU DON'T, SORRY FOR THE INCONVENIENCE (ALTERNATIVELY YOU CAN CHANGE THE INSTALLATION PATH WITHIN THE INSTALLER ITSELF TO THE CORRECT LOCATION)**

## Showcase

<p align="center">
  <img src="git_graphics/homepage.png" alt="Home Page" width="800">
  <br><i>Home Page</i><br><br>
  <img src="git_graphics/browserpage.png" alt="Browser" width="800">
  <br><i>Browser</i><br><br>
  <img src="git_graphics/favoritespage.png" alt="Favorites" width="800">
  <br><i>Favorites</i><br><br>
  <img src="git_graphics/downloadspage.png" alt="Downloads" width="800">
  <br><i>Downloads</i><br><br>
  <img src="git_graphics/hentaipage.png" alt="Hentai Tab" width="800">
  <br><i>Hentai Tab</i><br><br>
  <img src="git_graphics/mangapage.png" alt="Manga Reader" width="800">
  <br><i>Manga Reader</i><br><br>
  <img src="git_graphics/minigamespage.png" alt="Minigames" width="800">
  <br><i>Minigames</i><br><br>
  <img src="git_graphics/aipage.png" alt="AI Assistant" width="800">
  <br><i>AI Assistant</i><br><br>
</p>

## Features

### Content & Sources
- **Multi Source Support**: Browse content from multiple built in sources:
  - Gelbooru, Danbooru, Konachan, Yandere, Rule34, Hypnohub, Waifu.pics, Zerochan
- **Combined Search**: Search across all sources simultaneously for a massive content pool.
- **Custom Sources**: Add your own favorite booru sites to the application.

### Media & Viewing
- **SNEK Apollo**: High performance (mhm mhm, yes yes), custom multimedia framework for video playback and streaming support.
- **Modern Image Formats**: Native support for AVIF and WebP images, ensuring compatibility with all modern imageboards and some a bit less modern.
- **FullScreen Viewer**: An immersive, multiprocess media viewer with zoom and video controls that won't freeze the app.
- **Manga Reader**: A dedicated tab for searching and reading manga from various online sources, complete with an integrated ad blocker.
- **Automatic Video Support**: Plays most video formats automatically (requires VLC Media Player).

### Search & Organization
- **Tag Based Searching**: Powerful tag search with auto completion to find exactly what you're looking for.
- **Reverse Image Search**: Find the source of an image using SauceNAO, IQDB, or Google Lens.
- **Favorites System**: Save your favorite posts for easy access.
- **Personalized Recommendations**: Get content suggestions based on your favorites and search history.
- **Bulk Downloading**: Download multiple posts at once with a progress tracker.
- **Blacklist System**: Filter out unwanted content using a personal tag blacklist.
- **Search History**: Quickly access your previous searches.
- **16+ Languages**: Fully localized interface supporting English, Polish, Russian, Spanish, Japanese, Korean, and many more.
- **Customizable Theming**: Style the entire application using a simple but powerful sCSS (snek CSS) system.
- **Incognito Mode**: Browse privately without affecting your history or recommendations.

### Fun & Games
- **Random Post/Tag**: Discover new content and tags with the click of a button.
- **Tag Suggestion System**: Get ideas for new tags to explore.
- **Multiple Minigames**: Test your knowledge and have fun with several built in games:
  - Post Showdown, Tag Guesser and Image Scramble!!

## Download
Windows precompilation only for now
- Link: [WIN_Snekbooru_Installer_x64](https://github.com/The-SNEK-Initiative/Snekbooru/releases/download/v6.0.0/WIN_Snekbooru_Installer_x64.exe)

## Installation

1. Run the Snekbooru installer (WIN_Snekbooru_Installer_x64.exe)
2. Follow the Iluvatar installation wizard
3. Launch Snekbooru from your Start Menu or desktop shortcut

### System Requirements

- Windows 7 or later (64-bit)
- 4GB RAM recommended
- VLC Media Player 64-bit (required for video playback)
- Internet connection

## First-Time Setup

1. On first launch, you'll be prompted to configure your settings.
2. **(Optional but Recommended)** Enter API keys for enhanced access:
   - Gelbooru: User ID and API Key
   - Danbooru: Login and API Key
   - Rule34: User ID and API Key
   - AI Chat: OpenRouter.ai API Key (free)

### Getting API Keys

- **Gelbooru**: Available with a [Gelbooru account](https://gelbooru.com/index.php?page=account&s=reg).
- **Danbooru**: Available with a [Danbooru account](https://danbooru.donmai.us/users/new).
- **Rule34**: Available with a [Rule34 account](https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=web&cd=&ved=2ahUKEwiBnqiH1KuPAxUrEhAIHQ4mIeoQFnoECAoQAQ&url=https%3A%2F%2Frule34.xxx%2Findex.php%3Fpage%3Daccount%26s%3Dreg&usg=AOvVaw3TBT0l81tteZ1h8o6JIaHA&opi=89978449).
- **AI Chat (OpenRouter)**: Get a free key from [OpenRouter.ai](https://openrouter.ai/), a gateway for various AI models.
- **AI Chat (Google DeepMind Gemini)**: Free key available with a [Google DeepMind account](https://ai.google.dev/gemini-api/docs).

The application works without API keys but may have reduced functionality or be subject to stricter rate limits.

## Basic Usage

### Searching
1. Select your preferred source from the sources tab in Settings.
2. Enter tags in the search box (e.g., "cat_ears rating:safe").
3. Click "Search" or press Enter.

### Downloading
- **Single File**: Click a thumbnail, then use the "Quick Download" button in the Post Inspector.
- **Bulk Download**: Ctrl/Shift+Click thumbnails to select them, then use the "Download Selected" button.

### Favorites
- Add/remove favorites via the star button in the Post Inspector or by right clicking a thumbnail.
- View all your favorites in the "Favorites" tab.
- Recommendations in the "Browser" tab improve based on your favorites and history.

### Reverse Image Search
1. Go to the "Browser" tab, then the "Reverse Search" subtab.
2. Drag and drop an image, paste an image from your clipboard, or upload a file. You can also paste an image URL.
3. Select a search engine (SauceNAO, IQDB, Google Lens).
4. Click "Search".

## Advanced Usage

### AI Chat
The AI tab provides a sophisticated chat interface with advanced capabilities.
- **Multi Chat**: Maintain multiple independent conversations with the AI.
- **Tool Integration**: The AI can now perform tasks for you, such as searching for images or inspecting specific posts.
- **Presets**: Switch between different AI models (OpenRouter, Gemini) and personas using the Presets menu.
- **Setup**: Go to `Settings -> AI API` to enter your OpenRouter and/or Gemini API keys.
- **Personalization**: Adjust creativity, tone, and verbosity sliders to fine tune the AI's responses.

### Customizing Appearance
Snekbooru uses a custom styling language called sCSS (snek CSS not sassy CSS) to give you full control over the application's look and feel.
1. Go to `Settings -> Appearance`.
2. Click "New" to create a new theme file. It will open in the built in sCSS editor, pre filled with an example.
3. Click "Styling Help" for a detailed guide on all available selectors and properties. (This also exists on the [website](https://www.snekbooru.org/theme-guide))
4. Save your changes, then select your new theme from the "Active Theme" dropdown.

### Adding Custom Sources
You can add other booru style websites to the application.
1. Go to `Settings -> Custom Sources`.
2. Click "New" to open the Booru Editor.
3. Use the "Simple" mode for common booru types (Gelbooru, Danbooru, Rule34) by just providing a name and URL.
4. Use the "Advanced" mode for full control over API endpoints for unsupported site types.
5. Test your configuration before saving. Your new source will appear in the sources tab in Settings.

## Troubleshooting

### Performance Tips
- Reduce the number of grid columns for slower connections
- Lower the thumbnail size if loading is slow
- Clear search history periodically for better performance

### Common Issues

1. **"Failed to load" on thumbnails**
   - Check your internet connection
   - The post might have been deleted from the source.
   - Try refreshing the page
   - A API may have changed since I published the last version and broken something in the app, its bullshit but just wait till I patch it.

2. **API Errors**
   - Verify your API keys in Settings.
   - You might be rate limited; wait a few minutes and try again.
   - Check if the source website is online

3. **Download Issues**
   - Ensure you have write permissions to the download folder
   - Check available disk space
   - Try changing the download location in Settings

4. **Languages not loading properly everywhere**
   - This is a known issue, the only fix right now is to restart the application.

## Support

For bug reports, feature requests, and community discussion, please join our Discord server or contact the developers.
- **Discord**: https://discord.gg/BqNxn7ftqn
- Creator: atroubledsnake
- Contributors: 69st (Discord), _shidouuu (Discord)

## Changelog
### Release Version 6.0.1
- **Security Audit & Hardening**:
  - Implemented URL encoding for all search queries to prevent injection vulnerabilities.
  - Enabled Content Security Policy (CSP) in the media viewer for improved browsing safety.
  - Sanitized file extensions during downloads to prevent path traversal risks.
- **Zerochan Integration Fixes**:
  - Removed unsupported rating tags that caused search failures.
  - Implemented automatic tag capitalization to match Zerochan's search requirements.
- **Danbooru Stability**:
  - Optimized search queries to stay within Danbooru's tag limits, resolving 422 errors.
- **Bug Fixes**:
  - Fixed a `NameError` in the Zerochan fetcher.
  - Added User-Agent headers to site statistic scraping to prevent connection resets on yande.re.
  - Hardened hardware ID retrieval by disabling shell execution.
### Release Version 6.0.0
- FINALLY got rid of VLC and Qt's video player, the app now uses its own video player that I wrote myself (I'll release the source code to SNEK_Apollo once I finish Linux compatibility)
- Added 4 new languages (Korean, Turkish, Dutch and Italian) and introduced a great number of changes to the prexisting lngpcks
- Multiple changes to the AI tab:
  - added tool use, the AI can now search for images, tags and even inspect posts for you
  - finally fixed how markdown was parsed
  - improved how the AI handles requests (it used to consume way more usage then intended)
- The new release uses SNEK_Iluvatar (to which I have released the source code on my [github](https://github.com/ATroubledSnake/SNEK_Iluvatar)) instead of Inno Setup
- Removed a shitton of old code that wasn't used anymore and refactored some other parts of the code
- Fixed ZeroChan thumbnails failing to load
- Replaced nHentai with e-Hentai in the manga tab (thank _shidouuu for the idea)
- Fixed a LOT of memory leak issues, so your device shouldn't explode after a while of using the app anymore
### Release Version 5.0.8 Patch
- Fixed issue with settings crashing the app on saving (I still have no idea how I let such a big error happen and how I let it into prod)
### Release Version 5.0.8
- **Video Playback Overhaul**: 
  - Switched from custom implementations to PyQt5's native QMediaPlayer for stability and reliability
  - Eliminated ffmpeg threading issues that were causing assertion errors
  - Added comprehensive video controls (Play/Pause, Seek, Volume, Skip)
- **Audio Improvements**: 
  - Native audio playback with volume control
  - Proper audio sync through Qt's multimedia engine
- **Tag Suggestion System**:
  - Auto-complete tag suggestions as you type (minimum 2 characters)
  - Manual tag suggestion dialog with visual selection
- **Hentai Tab**: 
  - New dedicated tab for hentai content with optimized browsing and discovery features
- **Custom Sources**: 
  - Brought back the ability to add and manage custom booru sources
  - Simple mode for common booru types and advanced mode for full API customization
- **Comprehensive Language Support**:
  - Updated all 12 language packs with complete translations for video controls, tag suggestions, and new features
  - Supported languages: German, Spanish, French, Croatian, Hindi, Japanese, Polish, Portuguese (Brazil & Portugal), Russian, Chinese (Simplified & Traditional)
- **Performance Improvements**:
  - Better memory management in media viewer
  - Optimized tag suggestion fetching with background workers
### Release Version 5.0.5
- Significantly improved the UI of the Manga tab by organizing controls into logical groups for a cleaner and more intuitive layout.
- Fixed an issue where the Browser tab's background color would not update correctly when changing application themes.
- Added a new Manga Reader feature that allows you to view manga from Nhentai and Mangadex.
### Release Version 5.0.3
- Fixed multiple bugs in the minigames tab and made all the minigames actually playable and enjoyable again.
- Multiple changes introduced to the donwloads tab allowing for local media import and minor bugfixes.
- Fixed random posts showing up only from Gelbooru.
### Release Version 5.0.2
- Introduced a better way to choose sources (via checkboxes) - this now allows mixing different sources instead of all or just one.
- Refactored the downloads tab:
    - Added tag saving
    - introduced thumbnail viewing.
- Refactored favorites tab:
    - Added categories/catalogues.
    - Changed the positioning and size of the post inspector.
- Minor stability improvements.
### Release Version 5.0.0
  - Overhauled the **AI Chat Assistant**:
    - Implemented response streaming for faster, more interactive conversations.
    - Added support for multiple, renameable chat tabs to organize conversations.
    - Introduced customizable AI Presets to easily switch between different AI models, names, and personalities.
  - Added a **Hotkeys** tab in Settings, allowing for full customization of application keyboard shortcuts.
  - Added a "Go to Page" input field for direct page navigation in the browser.
  - Changed settings layout for a more user-friendly experience.
    - Added special toggles to quickly blacklist harmful content.
    - Grouped all API keys into one singular tab for ease of use.
    - Fixed bugs involved with styling the settings tab.
  - General stability improvements and major bug fixes.
### Release Version 4.9.4
  - Added AI Chat Assistant with advanced personalization options.
  - Added Reverse Image Search tab with support for SauceNAO, IQDB, and Google Lens.
  - Added a link to the official Discord server on the home page.
  - Completely overhauled the README with detailed documentation for all features.
  - Minor bug fixes and performance improvements.
### Release version 4.8.7
  - Added custom styling using sCSS (documentation provided in settings)
  - Added support for multiple languages
  - New logo and improved scraping
  - Added incognito mode
  - Added a section for adding your own api
  - Improved the recommendations bot even further
  - Fixed multiple visual bugs
### Release Version 4.8
  - Fixed major bug causing frequent crashes in the video player.
  - Added more and improved video and sound controls.
  - Upgraded the recommendations robot.
### Release Version 4.7.4
  - Multiprocessing implemented in order to stop app from crashing if a media causes VLC to crash.
### Release Version 4.6.1
  - Fixed major bug causing crashes after searching for a second time.
## Credits

- Creator & Developer: atroubledsnake
- Developers: meowaste and rxnd0m_dev (Thank them for the CS version!)
- Testers & Idea Contributors: 69st, _shidouuu and nikolailol

Special thanks to all users who provided feedback and suggestions!

## Changelog
### Release Version 6.0.2
- Fixed an issue making ImageViewer crash on start
- Moved Snekbooru fully to python 3.14 from python 3.11
- Fixed a few more security issues
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
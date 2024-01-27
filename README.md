# Audio Renamer

AudioRenamer is a python script based on the [Mutagen](https://github.com/quodlibet/mutagen) library designed to make the directory structure of your music match the metadata it contains.

It has been written with Windows in mind, but should be applicable to both Linux and MacOS systems with minimal changes. 

## Setup
AudioRenamer makes use of three python libraries; Mutagen, Pillow, and Spotipy. All of these can be installed through pip.

If Spotify integration is desired for automatic album artwork downloading, a [Spotify Developer](https://developer.spotify.com/) account is required, then an app must be created, and the client ID and secret must be entered into secrets.py to enable access to their API.

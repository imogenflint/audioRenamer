import argparse
import os
import re
import shutil
from dataclasses import dataclass
import urllib.request as request

from secrets import secrets

import mutagen
import mutagen.id3 as id3
import spotipy
from PIL import Image
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from spotipy.oauth2 import SpotifyClientCredentials

# Compile regex to remove invalid filename characters for windows
invalid_chars = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

# Define relevant tag names for different formats
mp3tags = 'TPE1', 'TALB', 'TIT2', 'TRCK', 'TPOS'
flactags = 'albumartist', 'album', 'title', 'tracknumber', 'discnumber'


# Define a dataclass to hold track metadata
@dataclass
class TrackMetadata:
    file: mutagen.File
    artist: str
    album: str
    title: str
    track: str
    disc: str
    file_type: str
    filename: str
    album_dir: str


def get_tags(album_dir: str):
    artist = None
    album = None

    if verbose:
        print("\nProcessing: " + album_dir)

    # Iterate over a directory
    for filename in os.listdir(album_dir):

        # Create full file paths for tracks
        filepath = os.path.join(album_dir, filename)

        # Flatten subdirectories
        if os.path.isdir(filepath):
            flatten_dir(album_dir, filepath)
            get_tags(album_dir)
            break

        elif filepath.endswith(".mp3") or filepath.endswith(".flac"):
            tags = None
            file = None
            file_type = None

            if filepath.endswith(".mp3"):
                # Load file to mp3 object
                file = MP3(filepath)
                tags = mp3tags
                file_type = '.mp3'
            elif filepath.endswith(".flac"):
                # Load file to a flac object
                file = FLAC(filepath)
                tags = flactags
                file_type = '.flac'

            # Read relevant track information from metadata
            artist = file.get(tags[0], [None])[0]
            album = file.get(tags[1], [None])[0]
            title = file.get(tags[2], [None])[0]
            track = file.get(tags[3], [None])[0]
            disc = file.get(tags[4], [None])[0]

            # Create a track metadata object to allow for easy processing
            track_data: TrackMetadata = TrackMetadata(file=file, artist=artist, album=album, title=title, track=track,
                                                      disc=disc, file_type=file_type, filename=filename,
                                                      album_dir=album_dir)
            process_metadata(track_data)

        elif filepath.endswith("cover.jpg"):
            pass

        else:
            # Remove anything that isn't audio or cover.jpg
            print("Other file found: " + filepath)

            if delete_auth or input("Delete this file? (Y/n): ").capitalize() == 'Y':
                os.remove(filepath)
                print("File removed")

    # Finally move the album folder to be correctly named
    # N.B. Album/artist data should be identical, so any track's metadata works
    album_dir = rename_dir(album_dir, artist, album)

    process_album_art(artist, album, album_dir)


def flatten_dir(parent_dir: str, source_dir: str):
    # List all files in the source directory
    files_to_move = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f))]

    # Move each file to the parent directory
    for file_name in files_to_move:
        source_path = os.path.join(source_dir, file_name)
        destination_path = os.path.join(parent_dir, file_name)
        shutil.move(source_path, destination_path)

    # Remove the now empty directory
    if len(os.listdir(source_dir)) == 0 and (delete_auth or input("Remove empty directory at" + source_dir + "? (Y/n): "
                                                                  ).capitalize() == 'Y'):
        os.rmdir(source_dir)


def clean_track_number(track: str, file: mutagen.FileType, file_type: str):
    # Remove x/y track numbering
    slash_index = track.find('/')
    if slash_index >= 0:
        track = track[:slash_index]

    # Remove 0 padding within track numbers
    if track[0] == '0':
        track = track[1:]

    # Write new track number to file
    if file_type == '.flac':
        file['tracknumber'] = track
    elif file_type == '.mp3':
        file['TRCK'] = id3.TRCK(encoding=3, text=track)
    file.save()

    # Return the track number
    return int(track)


def generate_title(disc: str, track_num: int, title: str, file_type: str):
    # Pad single digit track numbers
    if int(track_num) < 10:
        track_num = "0" + str(track_num)

    # Add the disc index to the track number if in a multi-disc album
    disc = disc.split('/')
    if int(disc[1]) > 1:
        track_num = "{}{}".format(disc[0], str(track_num))

    # Generate and return the correct track name
    track_name = str(track_num) + ". " + title + file_type
    return track_name


def rename_track(src_name: str, dest_name: str, album_dir: str):
    # Regex match and replace invalid characters with an empty string
    dest_name = re.sub(invalid_chars, '', dest_name)

    # Update non-matching filenames
    if src_name != dest_name:
        os.rename(album_dir + "\\" + src_name, album_dir + "\\" + dest_name)
        print("Renamed " + src_name + " to " + dest_name + " in " + album_dir)


def process_metadata(data: TrackMetadata):
    track_number = clean_track_number(data.track, data.file, data.file_type)

    track_name = generate_title(data.disc, track_number, data.title, data.file_type)

    rename_track(data.filename, track_name, data.album_dir)


def rename_dir(album_dir: str, album_artist: str, album_title: str):
    # Remove invalid characters from artist and title
    album_artist = re.sub(invalid_chars, '', album_artist)
    album_title = re.sub(invalid_chars, '', album_title)

    # Generate path for new directory
    new_dir = directory + '\\' + album_artist + " - " + album_title

    # Removes a trailing dot which windows will remove anyways, prevents infinite renames
    if new_dir[-1] == '.':
        new_dir = new_dir[:-1]

    # Move the directory
    if album_dir != new_dir:
        os.rename(album_dir, new_dir)
        print("Moved " + album_dir + " to " + new_dir)

    return new_dir


def process_album_art(artist: str, album: str, album_dir: str):
    valid_art = False
    cover_path = album_dir + "\\cover.jpg"

    # If cover.jpg exists, check that it is the correct size
    if os.path.isfile(cover_path):
        with Image.open(cover_path) as img:
            width, height = img.size
            if width == 400 and height == 400:
                valid_art = True
            else:
                print("Incorrect cover size at: " + album_dir)

    if not valid_art and enable_spotify:
        # Assemble a valid query for spotify
        search_string = "album:" + album + " artist:" + artist
        search_string.replace(' ', "%20")

        # Query spotify and get the highest res. image url
        query_dict = sp.search(search_string, 1, 0, "album")

        # Ensure at least one album is found
        if query_dict['albums']['total'] > 0:

            image_url = query_dict['albums']['items'][0]['images'][0]['url']

            # Save image to disk
            request.urlretrieve(image_url, cover_path)

            # Crop and resize image to 400x400
            image = Image.open(cover_path)

            if image.width != image.height:
                crop_to = min(image.width, image.height)

                image = image.crop((0, 0, crop_to, crop_to,))

            image.thumbnail((400, 400))
            image.save(cover_path)

            print("Saved new artwork to " + album_dir)

        else:
            print(artist + " - " + album + " could not be found on spotify, find artwork manually")


# Create a parser to take arguments
parser = argparse.ArgumentParser()
parser.add_argument('directory', help='the directory to process')
parser.add_argument('-v', '--verbose', action='store_true', help='if set, increase output verbosity')
parser.add_argument('-d', '--delete_auth', action='store_true', help='if set, automatically delete unwanted'
                                                                         ' files without prompt')
parser.add_argument('-s', '--enable_spotify', action='store_true', help='if set, use spotifys api to '
                                                                            'download album art')

# Assign arguments to values
args = parser.parse_args()
directory = args.directory
verbose = args.verbose
delete_auth = args.delete_auth
enable_spotify = args.enable_spotify

if verbose:
    print(args)

if enable_spotify:
    # Create spotipy credentials structs (needs SPOTIPY_CLIENT_ID & SPOTIPY_CLIENT_SECRET env variables to be set)
    auth_manager = SpotifyClientCredentials(secrets.get('SPOTIPY_CLIENT_ID'), secrets.get('SPOTIPY_CLIENT_SECRET'))
    sp = spotipy.Spotify(auth_manager=auth_manager)

# Iterate over each sub-directory in the passed one
for dirName in os.listdir(directory):
    get_tags(os.path.join(directory, dirName))

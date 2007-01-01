#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""kolmogorov, a fast python/curses front-end to mpg123/ogg123/flac123
Copyright (C) 2007  G. G. Venturini
 
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
 
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>."""

import os, sys, getopt, curses, signal, subprocess, time, thread, imp

VERSION = "0.051beta"
# KNOWN_EXTENSIONS must be all lowercase
KNOWN_EXTENSIONS = ["mp3", "mp2", "flac", "ogg", "wav", "aac", "mp4"]

# Each player has a dictionary with keys:
# command: a string, the command to invoke the player
# options: a list of strings, each string is a option or a option's value
# (order sensitive, obviously)
# There is also a key for each known audio extension. 
# The value is a boolean. If True, the player can play the format.

MPLAYER = {"command":"mplayer", \
    "options":["-quiet", "-vo", "null", "-cache", "1024"], \
    "mp3":True, "mp2":True, "flac":True, "ogg":True, "wav":True, \
    "aac":True, "mp4":True}
MPG123 = {"command":"mpg123", "options":["-q"], "mp3":True, "mp2":True, \
    "flac":False, "ogg":False, "wav":False, "aac":False, "mp4":False}
MPG321 = {"command":"mpg321", "options":["-q"], "mp3":True, "mp2":True, \
    "flac":False, "ogg":False, "wav":False, "aac":False, "mp4":False}
OGG123 = {"command":"ogg123", "options":["-q"], "mp3":False, "mp2":False, \
    "flac":False, "ogg":True, "wav":False, "aac":False, "mp4":False}
FLAC123 = {"command":"flac123", "options":["-q"], "mp3":False, "mp2":False, \
    "flac":True, "ogg":False, "wav":False, "aac":False, "mp4":False}

KNOWN_PLAYERS = (MPLAYER, MPG123, MPG321, OGG123, FLAC123)

TAG_SUPPORT = True
try:
    imp.find_module("mutagen")
    #import mutagen, mutagen.mp3, mutagen.easyid3
except ImportError:
    TAG_SUPPORT = False

def usage():
    """Prints usage info.
    
    Returns: None
    """
    print "kolmogorov " + VERSION + " written by G. G. Venturini, (c) 2007\n"
    print "kolmogorov is a (very) lightweight iTunes clone for *Unix boxes :).\n"
    print "Released under GPL v3. See: http://www.gnu.org/copyleft/gpl.html\n"
    print "This program is a python/curses front-end for mpg123, ogg123,"
    print "flac123 and mplayer. It may be extended to support more players."
    print "\nUsage: \n\tkolmogorov [options] [/path/to/music/files]\n"
    print "  or\n\tkolmogorov [options] [/path/to/playlist.m3u]\n"
    print " The path to music files is a directory. It may be omitted, if so,"
    print " kolmogorov will try to load ~/.kolmogorov_playlist.m3u where the"
    print " last playlist was saved on quit. If it doesn't exist, it will halt."
    print "\nAvailable options are:"
    print "\t-p (--players)\tprint a list of known audio formats and players."
    print "\t-h (--help)\tprint this help and quit."
    print "\t-L (--license)\t print info about this software's license terms."
    print "\t-r (--recursive)\tload recursively all subdirs too."
    print "\t-s (--sort)\tsort playlist (case insensitive)."
    print "\t-t (--tag)\tprints if there is tag support."
    print "\t-V (--version)\tprint version and quit."
    print "\nAvailable commands in curses mode:"
    print " up/down arrows (or j-k), page-up/page-down, home/end move the cursor."
    print " <space>/<enter>\tplay song under cursor."
    print " +\tadd selected song to playing queue."
    print " -\tremove selected song from playing queue."
    print " S\tshow playing song."
    print " s\tcase-insensitive sort of playlist."
    print " c\tenable or disable continuos play mode."
    print " T\tswitch between tag information and filename."
    print " r\trefresh screen."
    print " q\tquit."

def is_m3u_playlist(filename):
    """Checks if a file is a m3u playlist.
    Returns: a boolean
    """
    fp = open(filename, "rb")
    firstline = fp.readline()
    if firstline.upper().strip() == "#EXTM3U":
        return True
    return False

def load_m3u(filename):
    """Loads a m3u playlist.

    m3u playlists contains the path to the music files.
    The paths may be relative (to the directory where the m3u was saved) or
    absolute. 

    filename is the absolute path to the m3u file.
    
    This function checks if the filenames in the m3u are relative or 
    absolute. 

    If they are relative, the directory of the file is used as base_path,
    and returned (see below).
    If they are absolute, it looks for a common prefix to all files in the
    playlist. If it's found, it's returned as base_path. Otherwise, 
    base_path is set to "".

    Returns: (file_list, base_path)

    file_list is a list of paths. The complete path to a file is always 
    given by os.path.join(base_path, file_list[index])
    """
    fp = open(filename, "rb")
    base_path = os.path.dirname(filename)
    file_list = []
    for line in fp:
        line = line.strip()
        if line[0] == '#':
            continue
        if not os.path.isabs(line):
            line = os.path.join(base_path, line)
        file_list = file_list + [line]
    fp.close()
    cp = os.path.commonprefix(file_list)
    if cp != "" and cp != os.path.sep:
        file_list = [af[len(cp):] for af in file_list]
    
    return file_list, cp

def write_m3u(file_list, base_path, filename):
    """Writes a m3u playlist to file.

    Filenames are always absolute.

    Returns: None
    """
    fp = open(filename, "wb")
    fp.write("#EXTM3U\n")
    for f in file_list:
        fp.write(os.path.join(base_path, f) + "\n")
    fp.close()

def print_players():
    """Prints to screen the list of known players and known extensions.

    For each player, it prints the audio formats it supports (which of the known
    extensions). If there is a '*' near the extension, it means that that player
    will be used by default to play that kind of files.

    Returns: None
    """
    support_dict = check_players(KNOWN_PLAYERS, KNOWN_EXTENSIONS)
    print "KNOWN_EXTENSIONS:"
    [ sys.stdout.write(a_ext+" ") for a_ext in KNOWN_EXTENSIONS ]
    #map(lambda i: sys.stdout.write(i+" "), KNOWN_EXTENSIONS)
    sys.stdout.write("\n")
    print "KNOWN_PLAYERS"
    count = 0
    for player in KNOWN_PLAYERS:
        count = count + 1
        print str(count) + ". " + player["command"]
        sys.stdout.write("options: ")
        for option in player["options"]:
            sys.stdout.write(option + " ")
        sys.stdout.write("\n")
        sys.stdout.write("supported formats: ")
        for ext in KNOWN_EXTENSIONS:
            if player[ext]:
                sys.stdout.write(ext)
                if support_dict.has_key(ext) \
                and support_dict[ext][0][0] == player["command"]:
                    sys.stdout.write("*")
                sys.stdout.write(" ")
        sys.stdout.write("\n")
    return None

def check_players(KNOWN_PLAYERS, KNOWN_EXTENSIONS):
    """ Checks if the supported and known players (mpg123, ogg123, 
    flac123...) are in the user path.

    Currently, it relies on the *NIX utility 'which'.

    Returns: 
    a python dictionary, usually called supported_dict that has a key for
    each known filetype and the corresponding value is a list of lists.
    Each list has string elements: the first is the player's command line name, the others
    are the options to be passed to it.
    Eg. {"mp3":[["mpg123", "-q"]]}
    """
    support_dict = {}
    
    for player in KNOWN_PLAYERS:
        s = subprocess.Popen(("which", player["command"]), stdin=subprocess.PIPE, \
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if s.wait() != 0: # file not found
            continue
        for ext in [k for k in KNOWN_EXTENSIONS if player[k]]:
            if support_dict.has_key(ext):
                support_dict[ext] = support_dict[ext] + [[player["command"]] + \
                    player["options"]]
            else:
                support_dict.update({ext:[[player["command"]] + player["options"]]})
            
    return support_dict

def is_file_supported(filename, supported_dict):
    """
    Returns: 
    True if the dictionary of supported file formats has a entry for the
    extension of filename and the value of it is True. 
    Otherwise returns False.
    """
    ext = os.path.splitext(filename)[1]
    if len(ext) > 1: # ext has the dot too
        ext = ext[1:].lower()
        if supported_dict.has_key(ext):
            supported = supported_dict[ext][0]
        else:
            supported = False
    else:
        supported = False
    return supported

def sanitize_string(astring):
    """Strips any character with ord(c) > 128"""
    ret = ""
    for achar in astring:
        if ord(achar) < 128:
            ret = ret + achar
    return ret

def sort_playlist(primary_list, sec_list, aindex):
    """Case-insensitive sorts the primary list.
    
    sec_list is ordered to reflect primary_list's new sorting.
    aindex is a index on a element in primary list. The method returns 
    the index of the same element in the sorted list."""

    if aindex is not None:
        avalue = primary_list[aindex]
    tmp_dict = {}
    for i in range(len(primary_list)):
        tmp_dict.update({primary_list[i]:sec_list[i]})
    primary_list.sort(cmp=lambda a, b: cmp(a.lower(), b.lower()))
    return_sec_list = []
    for i in range(len(primary_list)):
        return_sec_list = return_sec_list + [tmp_dict[primary_list[i]]]
    if aindex is not None:
        ret_index = primary_list.index(avalue)
    else:
        ret_index = None
    return primary_list, return_sec_list, ret_index

def read_file_list(base_path, supported_dict, recursive=False):
    """Reads the list of files in the directory base_path, filters the supported
    files through supported_dict.

    If recursive == True: load recursively all subdirs.

    Returns: the filtered list of filenames."""
    
    #_debug = True
    #if _debug:
    #    fp = open("/home/joseph/.kolmogorov.debug", "w")
    #    fp.write("Recursive: " + str(recursive))
    file_list = []
    for root, dirs, files in os.walk(base_path):
        #if _debug:
        #    fp.write("R, D, F: "+ str(root) +" "+ str(dirs) +" "+ str(files) + "\n")
        #    fp.write("file_list: "+str(file_list) + "\n")
        if os.path.samefile(base_path, root):
            file_list = file_list + files
            if not recursive:
                break
        else:
            temp_root = root
            temp_top = ""
            while(True):
                base, top = os.path.split(os.path.normpath(temp_root))
                temp_top = os.path.join(top, temp_top)
                if os.path.samefile(base, base_path):
                    file_list = file_list + [os.path.join(temp_top, af) for af in files]
                    break
                else:
                    temp_root = base
    
    file_list = [ af for af in file_list if is_file_supported(af, supported_dict) ]
    
    #if _debug:
    #    fp.close()
    return file_list

def select_and_update_tag_list(file_list, tag_list, text_index, \
        n_of_lines_on_screen, base_dir, n_of_cols_on_screen):
    """When tag-mode is enabled, each line shows tag information (where
    available and supported) and some audio information.

    See the help for build_label_from_tag(...)

    Since reading this information from each file takes some time, we wish
    to do it only for displayed files. The information about the remaining
    files in file_list should be read when the list is scrolled by the user
    and they become visible.

    There is an exception: if the user wants to sort the list we have to
    build all of the lines' strings, before sorting :|.

    file_list is the list of relative paths to the audio files in the
    playlist. When tagmode is off, each relative path is shown on its line.
    
    The tag-info-label corresponding to a file file_list[i] is tag_list[i].
    If it hasn't been built yet, tag_list[i] defaults to None.

    This method reads only information for the files in file_list in the 
    range(text_index, text_index + n_of_lines_on_screen).

    
    Returns: the updated tag_list.
    """
    
    for i in range(text_index, min(text_index + n_of_lines_on_screen, len(file_list))):
        if tag_list[i] is None:
            tag_list[i] = build_label_from_tag(os.path.join(base_dir, file_list[i]), n_of_cols_on_screen)
    return tag_list

def build_label_from_tag(filename, n_of_cols):
    """
    The label is built with this format:
    artist - album - tracknum - title   <white space>   type bitrate length

    This function uses the mutagen module to actually read tags and the
    other info.
    

    Returns: the label (a unicode string)
    """
    try:
        mutagen.version
    except NameError:
        import mutagen, mutagen.mp3, mutagen.easyid3

    if filename.lower().endswith(".mp3"):
        audio = mutagen.mp3.MP3(filename, ID3=mutagen.easyid3.EasyID3)
    else:
        audio = mutagen.File(filename)
    
    if audio is not None and len(audio.keys()) \
    and audio.has_key("title") and len(audio["title"][0]) and not audio["title"][0].isspace() \
    and audio.has_key("artist") and len(audio["artist"][0]) and not audio["artist"][0].isspace():
        tag_label = audio["artist"][0]
        if audio.has_key("album") and len(audio["album"][0]) and not audio["album"][0].isspace():
            tag_label = tag_label + " - " + audio["album"][0]
        if audio.has_key("tracknumber") and len(audio["tracknumber"][0]) and not audio["tracknumber"][0].isspace():
            track_num_splitted = audio["tracknumber"][0].split("/")
            tracknumber = audio["tracknumber"][0]
            if track_num_splitted[0].isdigit():
                try:
                    if int(track_num_splitted[0]) < 10 and int(track_num_splitted[0]) > 0 \
                    and len(track_num_splitted[0]) == 1:
                        tracknumber = "0" + track_num_splitted[0]
                        if len(track_num_splitted) == 2:
                            tracknumber = tracknumber + "/" + track_num_splitted[1]
                except ValueError:
                    pass
            tag_label = tag_label + " - " + tracknumber
        tag_label = tag_label + " - " + audio["title"][0]
    else:
        tag_label = filename.split(os.sep)[-1]
    
    info_label = None
    if audio is not None:
        #Now we build the audio info part of the string
        info_label = ""
        if audio.mime[0].index("/") > -1:
            info_label = info_label + audio.mime[0].split("/")[1]
        else:
            info_label = info_label + audio.mime[0]
        if hasattr(audio.info, "bitrate"):
            info_label = info_label + "  " + " "*(audio.info.bitrate / 1000 < 100) + str(audio.info.bitrate / 1000) + "Kbps"
        info_label = info_label + " " + " "*(audio.info.length / 60 < 10) + str(int(audio.info.length / 60)) + ":" 
        info_label = info_label + "0"*(audio.info.length % 60 < 10) + str(int(audio.info.length % 60))
        info_label = info_label + " "
        
        #put all together
        if len(tag_label) + len(info_label) < n_of_cols:
            tag_label = tag_label + (n_of_cols - len(tag_label) - len(info_label))*" " + info_label
        else:
            tag_label = tag_label[:n_of_cols - len(tag_label) - len(info_label) - 4] + "... " + info_label

    #try:
    #    tag_label = unicode(tag_label)
    #except UnicodeDecodeError:
    #    tag_label = unicode(string.decode(tag_label))
    
    return sanitize_string(tag_label)

def play_thread(play_status_dict, play_status_lock, display_status_dict, \
    display_status_lock, base_dir, support_dict):
    """ The playing thread. 
    Starts songs and repaints the screen when the playing song changes.
    
    
    Returns: This method _never_ returns.
    """
    play_process = None
    while True:
        play_status_lock.acquire()
        
        if play_status_dict["todo"] == "start_song":
            filename = play_status_dict["queue_file"].pop(0)
            
            if play_process is not None and play_process.poll() is None:
                os.kill(play_process.pid, signal.SIGTERM)
            
            ext = os.path.splitext(filename.lower())[1]
            if len(ext) and ext[0] == ".":
                ext = ext[1:]
            if support_dict.has_key(ext):
                play_process = subprocess.Popen(support_dict[ext][0] + [filename], \
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, \
                    stderr=subprocess.STDOUT)
                play_status_dict["pp_pid"] = play_process.pid
                
            play_status_dict["todo"] = "do_nothing"
        
        elif play_status_dict["todo"] == "stop_song":
            if play_process is not None and play_process.poll() is None:
                os.kill(play_process.pid, signal.SIGTERM)
            
            play_process = None
            play_status_dict["pp_pid"] = None
            play_status_dict["todo"] = "do_nothing"
        
        elif play_status_dict["todo"] == "do_nothing":
            pass
        
        play_status_lock.release()

        if play_process is not None and play_process.poll() is not None:
            play_status_lock.acquire()
            if len(play_status_dict["queue_index"]) \
            and len(play_status_dict["queue_file"]):
                play_status_dict["todo"] = "start_song"
                display_status_lock.acquire()
                display_status_dict["abs_hilighted_line"] = \
                    play_status_dict["queue_index"].pop(0)
                play_status_lock.release()
            elif display_status_dict["abs_hilighted_line"] + 1 < \
            len(display_status_dict["file_list"]) and play_status_dict["continue"]:
                play_status_dict["todo"] = "start_song"
                play_status_dict["queue_file"].append(os.path.join(base_dir, \
                    display_status_dict["file_list"][display_status_dict["abs_hilighted_line"]+1]))
                play_status_lock.release()
                display_status_lock.acquire()
                display_status_dict["abs_hilighted_line"] = display_status_dict["abs_hilighted_line"] + 1
            else:
                play_process = None
                play_status_dict["pp_pid"] = None
                play_status_lock.release()
                display_status_lock.acquire()
                display_status_dict["abs_hilighted_line"] = None
            
            if display_status_dict["tag_mode"]:
                paint_list = display_status_dict["tag_list"]
            else:
                paint_list = display_status_dict["file_list"]
            
            paint_screen(display_status_dict["stdscr"], paint_list, \
                display_status_dict["current_cursor_line"], \
                display_status_dict["current_text_line"], \
                display_status_dict["abs_hilighted_line"], \
                play_status_dict["queue_index"], display_status_dict["base_path"], \
                play_status_dict["continue"])
            
            display_status_lock.release()

        else:
            time.sleep(0.4)
        time.sleep(0.3)

def paint_screen(stdscr, file_list, line_index, text_index, hl_abs_index, queue, title, continuous):
    """Paints the screen.
    
    Returns: None
    """
    if len(file_list) > curses.LINES - 2:
        percentual_str = str((100*(text_index + curses.LINES - 2))/(len(file_list))) + "%"
    else:
        percentual_str = "100%"
    stdscr.border()
    stdscr.addstr(0, (curses.COLS-len(title))/2, title)
    stdscr.addstr(curses.LINES-1, 2, "kolmogorov " + VERSION)
    stdscr.addstr(curses.LINES-1, 6 + len("kolmogorov " + VERSION) + (4 - len(percentual_str)), percentual_str)
    if continuous:
        stdscr.addstr(curses.LINES-1, 14 + len("kolmogorov " + VERSION), "CONT")
    
    max_i = min(len(file_list) - text_index, curses.LINES - 2)
    for i in range(max_i):
        if len(file_list[i + text_index]) > curses.COLS - 8:
            filename = file_list[i + text_index][:curses.COLS-8]
        else:
            #print  file_list[i + text_index]
            filename = file_list[i + text_index] + " "*(curses.COLS - 8 - len(file_list[i + text_index]))
        if queue.count(i + text_index):
            queue_index = str(1 + queue.index(i + text_index))
            stdscr.addstr(i+1, 2 , " "*(len(queue_index)==1) + queue_index)
        else:
            stdscr.addstr(i+1, 2, "   ")
        if hl_abs_index == i + text_index or i == line_index:
            if hl_abs_index == i + text_index and i == line_index:
                stdscr.addch(i+1, 5, curses.ACS_DIAMOND)
                stdscr.addch(i+1, 6, " ")
                stdscr.addstr(i+1, 7, filename, curses.A_STANDOUT + curses.A_BOLD)
            elif hl_abs_index == i + text_index:
                stdscr.addstr(i+1, 5, "  ")
                stdscr.addstr(i+1, 7, filename, curses.A_STANDOUT) 
            elif i == line_index:
                stdscr.addch(i+1, 5, curses.ACS_DIAMOND)
                stdscr.addch(i+1, 6, " ")
                stdscr.addstr(i+1, 7, filename, curses.A_BOLD)
        else:
            stdscr.addstr(i + 1, 5, "  " + filename)
    stdscr.refresh()

def main(stdscr, file_list, base_dir, support_dict):
    """The main method. It holds the main while cycle.
    
    Returns: This method _never_ returns. It calls sys.exit
    
    Notice that this is different from the __name__ == '__main__' section
    In that section the options are processed, the file list is read, we 
    decide which type of audio file we can play and with which programs.

    This is the player main method. Here keystrokes are processed.
    """
    tag_list = [None]*len(file_list)
    display_status_dict = {"current_cursor_line":0, "current_text_line":0, "abs_hilighted_line":None, "stdscr":stdscr, \
            "tag_mode":False, "file_list":file_list, "tag_list":tag_list, "base_path":base_dir}
    display_status_lock = thread.allocate_lock()
    
    tot_lines = len(file_list)
    
    play_status_dict = {"queue_file":[], "queue_index":[], "todo":"do_nothing", "pp_pid":None, "continue":True}
    play_status_lock = thread.allocate_lock()
    
    thread.start_new_thread(play_thread, (play_status_dict, play_status_lock, display_status_dict, display_status_lock, \
        base_dir, support_dict))

    # main loop: paint the screen, get a char, act accordigly, rinse, repeat
    # may switch to non-blocking getch...
    while(True):
        display_status_lock.acquire()
        if display_status_dict["tag_mode"]:
            display_status_dict["tag_list"] = select_and_update_tag_list(display_status_dict["file_list"], \
                display_status_dict["tag_list"], display_status_dict["current_text_line"], curses.LINES - 2, \
                base_dir, curses.COLS - 8)
            paint_list = display_status_dict["tag_list"]
        else:
            paint_list = display_status_dict["file_list"]
        paint_screen(display_status_dict["stdscr"], paint_list, \
            display_status_dict["current_cursor_line"], display_status_dict["current_text_line"], \
            display_status_dict["abs_hilighted_line"], play_status_dict["queue_index"], \
            display_status_dict["base_path"], play_status_dict["continue"])
        display_status_lock.release()
        
        ch = stdscr.getch()
        
        if ch == ord("q"):
            play_status_lock.acquire()
            if play_status_dict["pp_pid"]:
                os.kill(play_status_dict["pp_pid"], signal.SIGTERM)
            play_status_lock.release()
            break
        
        elif ch == curses.KEY_DOWN or ch == ord("j"): 
            if display_status_dict["current_cursor_line"] + 1 < min(curses.LINES - 2, tot_lines):
                display_status_lock.acquire()
                display_status_dict["current_cursor_line"] = display_status_dict["current_cursor_line"] + 1
                display_status_lock.release()
            elif display_status_dict["current_text_line"] + display_status_dict["current_cursor_line"] + 1 < tot_lines:
                display_status_lock.acquire()
                display_status_dict["current_text_line"] = display_status_dict["current_text_line"] + 1
                display_status_lock.release()
        
        elif ch == curses.KEY_UP or ch == ord("k"):
            if display_status_dict["current_cursor_line"] > 0:
                display_status_lock.acquire()
                display_status_dict["current_cursor_line"] = display_status_dict["current_cursor_line"] - 1
                display_status_lock.release()
            elif display_status_dict["current_text_line"] > 0:
                display_status_lock.acquire()
                display_status_dict["current_text_line"] = display_status_dict["current_text_line"] - 1
                display_status_lock.release()
        
        elif ch == curses.KEY_NPAGE:
            step = curses.LINES - 4
            if display_status_dict["current_text_line"] + step + curses.LINES - 2 < tot_lines:
                display_status_lock.acquire()
                display_status_dict["current_text_line"] = display_status_dict["current_text_line"] + step
                display_status_dict["current_cursor_line"] = 0
                display_status_lock.release()
            elif tot_lines > curses.LINES - 2:
                display_status_lock.acquire()
                display_status_dict["current_text_line"] = tot_lines - curses.LINES + 2
                display_status_dict["current_cursor_line"] = curses.LINES - 3
                display_status_lock.release()
            else:
                display_status_lock.acquire()
                display_status_dict["current_cursor_line"] = tot_lines - 1
                display_status_lock.release()
        
        elif ch == curses.KEY_PPAGE:
            step = curses.LINES - 4
            if display_status_dict["current_text_line"] - step > 0:
                display_status_lock.acquire()
                display_status_dict["current_text_line"] = display_status_dict["current_text_line"] - step
            else:
                display_status_lock.acquire()
                display_status_dict["current_text_line"] = 0
            display_status_dict["current_cursor_line"] = 0
            display_status_lock.release()
        
        elif ch == curses.KEY_END:
            display_status_lock.acquire()
            display_status_dict["current_cursor_line"] = min(tot_lines, curses.LINES - 2) - 1
            display_status_dict["current_text_line"] = max(tot_lines, curses.LINES - 2) - curses.LINES + 2
            display_status_lock.release()
        
        elif ch == curses.KEY_HOME:
            display_status_lock.acquire()
            display_status_dict["current_cursor_line"] = 0
            display_status_dict["current_text_line"] = 0
            display_status_lock.release()
        
        elif ch == curses.KEY_ENTER or ch == ord(" "):
            if display_status_dict["abs_hilighted_line"] == display_status_dict["current_text_line"] + \
            display_status_dict["current_cursor_line"]:
                display_status_lock.acquire()
                display_status_dict["abs_hilighted_line"] = None
                display_status_lock.release()
                play_status_lock.acquire()
                play_status_dict["todo"] = "stop_song"
                play_status_lock.release()
            else:
                display_status_lock.acquire()
                display_status_dict["abs_hilighted_line"] = display_status_dict["current_text_line"] + \
                    display_status_dict["current_cursor_line"]
                display_status_lock.release()
                
                play_status_lock.acquire()
                if not len(play_status_dict["queue_index"]) \
                        or play_status_dict["queue_index"][0] != \
                        display_status_dict["current_text_line"] + display_status_dict["current_cursor_line"]:
                    play_status_dict["queue_file"].insert(0, \
                        os.path.join(base_dir, display_status_dict["file_list"][display_status_dict["current_text_line"] \
                        + display_status_dict["current_cursor_line"]]))
                elif play_status_dict["queue_index"][0] == \
                        display_status_dict["current_text_line"] + display_status_dict["current_cursor_line"]:
                    play_status_dict["queue_index"].pop(0)
                #play_status_dict["queue_index"].insert(0, display_status_dict["abs_hilighted_line"])
                play_status_dict["todo"] = "start_song"
                play_status_lock.release()
        
        elif ch == ord("+"):
            play_status_lock.acquire()
            if not play_status_dict["queue_index"].count(display_status_dict["current_text_line"] + \
                    display_status_dict["current_cursor_line"]):
                play_status_dict["queue_index"].append(display_status_dict["current_text_line"] + \
                    display_status_dict["current_cursor_line"])
                play_status_dict["queue_file"].append(os.path.join(base_dir, \
                    display_status_dict["file_list"][display_status_dict["current_text_line"] + \
                    display_status_dict["current_cursor_line"]]))
            play_status_lock.release()
        
        elif ch == ord("-"):
            play_status_lock.acquire()
            if play_status_dict["queue_index"].count(display_status_dict["current_text_line"] + \
                    display_status_dict["current_cursor_line"]):
                play_status_dict["queue_file"].pop(play_status_dict["queue_index"]\
                    .index(display_status_dict["current_text_line"] + display_status_dict["current_cursor_line"]))
                play_status_dict["queue_index"].remove(display_status_dict["current_text_line"] + \
                    display_status_dict["current_cursor_line"])
            play_status_lock.release()
        
        elif ch == ord("c"):
            play_status_lock.acquire()
            play_status_dict["continue"] = not play_status_dict["continue"]
            play_status_lock.release()
        
        elif ch == ord("S"):
            if display_status_dict["abs_hilighted_line"] is not None and \
                    display_status_dict["abs_hilighted_line"] < display_status_dict["current_text_line"] or \
                    display_status_dict["abs_hilighted_line"] > display_status_dict["current_text_line"] + \
                    curses.LINES + 2 - 5: # wtf shouldn't this be -1 ??
                display_status_lock.acquire()
                if len(display_status_dict["file_list"]) - display_status_dict["abs_hilighted_line"] >= curses.LINES -2:
                    display_status_dict["current_text_line"] = display_status_dict["abs_hilighted_line"] - \
                        1*(display_status_dict["abs_hilighted_line"] > 0)
                    display_status_dict["current_cursor_line"] = 1 
                else:
                    display_status_dict["current_text_line"] = len(display_status_dict["file_list"]) - curses.LINES -2 +4
                    display_status_dict["current_cursor_line"] = display_status_dict["abs_hilighted_line"] - \
                        display_status_dict["current_text_line"]
                display_status_lock.release()
        
        elif ch == ord("s"):
            if not display_status_dict["tag_mode"]:
                display_status_lock.acquire()
                display_status_dict["file_list"], display_status_dict["tag_list"], \
                    display_status_dict["abs_hilighted_line"] = \
                    sort_playlist(display_status_dict["file_list"], display_status_dict["tag_list"], \
                    display_status_dict["abs_hilighted_line"])
                display_status_lock.release()
            else:
                display_status_lock.acquire()
                # First we need to read all tags, then we can sort.
                display_status_dict["tag_list"] = select_and_update_tag_list(display_status_dict["file_list"], \
                    display_status_dict["tag_list"], 0, len(display_status_dict["file_list"]), base_dir, curses.COLS -8)
                
                display_status_dict["tag_list"], display_status_dict["file_list"], \
                    display_status_dict["abs_hilighted_line"] = \
                    sort_playlist(display_status_dict["tag_list"], display_status_dict["file_list"], \
                    display_status_dict["abs_hilighted_line"])
                display_status_lock.release()

        
        elif ch == ord("T") and TAG_SUPPORT:
            display_status_lock.acquire()
            display_status_dict["tag_mode"] = not display_status_dict["tag_mode"]
            display_status_lock.release()
        
        elif ch == ord("r"):
            display_status_lock.acquire()
            stdscr.clearok(1)
            display_status_lock.release()
    # end of while
    write_m3u(display_status_dict["file_list"], base_dir, os.path.expanduser("~/.kolmogorov_playlist.m3u"))
    #fp = open(os.path.expanduser("~/.kolmogorov_playlist"), "w")
    #cPickle.dump((base_dir, display_status_dict["file_list"]), fp)
    #fp.close()
    sys.exit(0)

if __name__ == '__main__':
    recursive = False
    sort = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hLVrstp", ("help", "license", "version", "recursive", "sort", "tag", "players"))
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    for option, a  in opts:
        if option in ("-h", "--help"):
            usage()
            sys.exit(9)
        if option in ("-L", "--license"):
            print __doc__
            sys.exit(0)
        if option in ("-V", "--version"):
            print VERSION
            sys.exit(10)
        if option in ("-p", "--players"):
            print_players()
            sys.exit(10)
        if option in ("-r", "--recursive"):
            recursive = True
        if option in ("-s", "--sort"):
            sort = True
        if option in ("-t", "--tag"):
            print "Tag support (through mutagen): " + str(TAG_SUPPORT)
            sys.exit(11)

    try:
        subprocess.Popen(("which", ), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    except OSError:
        print "Error: Kolmogorov requires the userland *NIX utility \"which\" to work."
        print "Add which to your PATH or hack the code and manually set mp3/ogg support."
        sys.exit(10)

    s = subprocess.Popen(("which", "ls"), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    if s.wait() != 0:
        print "Error: Kolmogorov requires the userland *NIX utility \"ls\" to work."
        print "Add which to your PATH or hack the code."
        sys.exit(10)
    
    support_dict = check_players(KNOWN_PLAYERS, KNOWN_EXTENSIONS)
    if len(support_dict) == 0:
        print "Error: Kolmogorov didn't find any supported player to play your media."
        print "Install and add to your PATH mpg123 or any other supported player."
        sys.exit(11)
    

    for ext in KNOWN_EXTENSIONS:
        if support_dict.has_key(ext) and len(support_dict[ext]) > 1:
            support_dict[ext] = [support_dict[ext][0]]
    
    #print args
    if len(args) != 1 and not os.path.exists(os.path.expanduser("~/.kolmogorov_playlist.m3u")):
        usage()
        sys.exit(2)
    elif len(args) == 1:
        base_path = args[0]
        base_path = os.path.realpath(os.path.abspath(os.path.expanduser(base_path)))

        if not os.path.isdir(base_path):
            if is_m3u_playlist(base_path):
                file_list, base_path = load_m3u(base_path)
                print base_path, file_list[0]
            else:
                print "Error: Kolmogorov doesn't play single files.\nYou can use mpg123/ogg123 directly."
                sys.exit(34)
        else:
            file_list = read_file_list(base_path, support_dict, recursive)
            if len(file_list) == 0:
                print "Error: empty file list."
                print base_path, "doesn't contain any supported file."
                sys.exit(12)    
    elif os.path.exists(os.path.expanduser("~/.kolmogorov_playlist.m3u")):
        file_list, base_path = load_m3u(os.path.expanduser("~/.kolmogorov_playlist.m3u"))
        #fp = open(os.path.expanduser("~/.kolmogorov_playlist.m3u"), "r")
        #base_path, file_list = cPickle.load(fp)
        #fp.close()

    if sort:
        file_list.sort(cmp=lambda a, b: cmp(a.lower(), b.lower()))
    
    #print support_dict
    stdscr = curses.wrapper(main, file_list, base_path, support_dict)


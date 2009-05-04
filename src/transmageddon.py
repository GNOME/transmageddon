#!/usr/bin/env python

# Transmageddon
# Copyright (C) 2009 Christian Schaller <uraeus@gnome.org>
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.



import sys
import os
import time
import transcoder_engine
import gobject; gobject.threads_init()
from urlparse import urlparse
import codecfinder
import about
import presets
import utils

from gettext import gettext as _
import gettext

try:
   import pygtk
   pygtk.require("2.0")
   import glib
   import gtk
   import gtk.glade
   import pygst
   pygst.require("0.10")
   import gst
   from gst.extend import discoverer
   import gst.pbutils
except:
   sys.exit(1)

start_time = time.time()

       
supported_containers = [
        "Ogg",
        "Matroska",
        "AVI",
        "MPEG TS",
        "FLV",
        "Quicktime",
        "MPEG4",
        "3GPP",
        "MXF"
]

supported_audio_codecs = [
       "vorbis",
       "flac",
       "mp3",
       "aac",
       "ac3",
       "speex",
       "celt",
#       "alac",
#       "wma2",
]

supported_video_codecs = [
       "theora",
       "dirac",
       "h264",
       "mpeg2",
       "mpeg4",
#       "wmv2",
       "xvid",
       "dnxhd",
]

class TransmageddonUI (gtk.glade.XML):
   """This class loads the Glade file of the UI"""
   def __init__(self):
       #Set up i18n
       for module in gtk.glade, gettext:
           module.bindtextdomain("transmageddon","../../share/locale")
           module.textdomain("transmageddon")

       #Set the Glade file
       self.gladefile = "transmageddon.glade"
       gtk.glade.XML.__init__ (self, self.gladefile)

       #Define functionality of our button and main window
       self.TopWindow = self.get_widget("TopWindow")
       self.FileChooser = self.get_widget("FileChooser")
       self.videoinformation = self.get_widget("videoinformation")
       self.audioinformation = self.get_widget("audioinformation")
       self.CodecBox = self.get_widget("CodecBox")
       self.presetchoice = self.get_widget("presetchoice")
       self.vorbisbutton = self.get_widget("vorbisbutton")
       self.flacbutton = self.get_widget("flacbutton")
       self.mp3button = self.get_widget("mp3button")
       self.aacbutton = self.get_widget("aacbutton")
       self.ac3button = self.get_widget("ac3button")
       self.speexbutton = self.get_widget("speexbutton")
       self.celtbutton = self.get_widget("celtbutton")
       self.alacbutton = self.get_widget("alacbutton")
       self.theorabutton = self.get_widget("theorabutton")
       self.diracbutton = self.get_widget("diracbutton")
       self.h264button = self.get_widget("h264button")
       self.mpeg2button = self.get_widget("mpeg2button")
       self.mpeg4button = self.get_widget("mpeg4button")
       self.wma2button = self.get_widget("wma2button")
       self.wmv2button = self.get_widget("wmv2button")
       self.xvidbutton = self.get_widget("xvidbutton")
       self.dnxhdbutton = self.get_widget("dnxhdbutton")
       self.containerchoice = self.get_widget("containerchoice")
       self.codec_buttons = dict()
       for c in supported_audio_codecs:
           self.codec_buttons[c] = self.get_widget(c+"button")
           self.codec_buttons[c].connect("clicked",
                                         self.on_audiobutton_pressed, c)
       for c in supported_video_codecs:
           self.codec_buttons[c] = self.get_widget(c+"button")
           self.codec_buttons[c].connect("clicked",
                                         self.on_videobutton_pressed, c)

       self.transcodebutton = self.get_widget("transcodebutton")
       self.ProgressBar = self.get_widget("ProgressBar")
       self.cancelbutton = self.get_widget("cancelbutton")
       self.StatusBar = self.get_widget("StatusBar")

       self.TopWindow.connect("destroy", gtk.main_quit)

       self.signal_autoconnect(self) # Initialize User Interface

       # Set the Videos XDG UserDir as the default directory for the filechooser, 
       # also make sure directory exists
       self.VideoDirectory = glib.get_user_special_dir(glib.USER_DIRECTORY_VIDEOS)
       CheckDir = os.path.isdir(self.VideoDirectory)
       if CheckDir == (False):
           os.mkdir(self.VideoDirectory)
       self.FileChooser.set_current_folder(self.VideoDirectory)

       # Setting AppIcon
       FileExist = os.path.isfile("../../share/pixmaps/transmageddon.png")
       if FileExist:
           self.TopWindow.set_icon_from_file("../../share/pixmaps/transmageddon.png")
       else:
           try:
               self.TopWindow.set_icon_from_file("transmageddon.png")
           except:
               print "failed to find appicon"

       # default all but top box to insensitive by default
       # self.containerchoice.set_sensitive(False)
       self.CodecBox.set_sensitive(False)
       self.transcodebutton.set_sensitive(False)
       self.cancelbutton.set_sensitive(False)
       self.presetchoice.set_sensitive(False)

       # set default values for various variables
       self.AudioCodec = "vorbis"
       self.VideoCodec = "theora"
       self.ProgressBar.set_text(_("Transcoding Progress"))

       self.p_duration = gst.CLOCK_TIME_NONE
       self.p_time = gst.FORMAT_TIME

       # Populate the Container format combobox
       self.lst = supported_containers
       for i in self.lst:
           self.containerchoice.append_text(i)
      
       # Populate presets combobox
       selected = 0
       for x, (id, device) in enumerate(sorted(presets.get().items(),
                                   lambda x, y: cmp(x[1].make + x[1].model,
                                                    y[1].make + y[1].model))):
           iter = self.presetchoice.append_text(str(device))
           if id == "computer":
               selected = x
       self.presetchoice.prepend_text("No Presets")

   # Create query on uridecoder to get values to populate progressbar 
   # Notes:
   # Query interface only available on uridecoder, not decodebin2)
   # FORMAT_TIME only value implemented by all plugins used
   # a lot of original code from gst-python synchronizer.py example
   def Increment_Progressbar(self): 
       try:
           position, format = self._transcoder.uridecoder.query_position(gst.FORMAT_TIME)
       except:
           position = gst.CLOCK_TIME_NONE

       try:
           duration, format = self._transcoder.uridecoder.query_duration(gst.FORMAT_TIME)
       except:
           duration = gst.CLOCK_TIME_NONE
       if position != gst.CLOCK_TIME_NONE:
           value = float(position) / duration
           if float(value) < (1.0) and float(value) >= 0:
               self.ProgressBar.set_fraction(value)
               percent = (value*100)
               timespent = time.time() - start_time
               percent_remain = (100-percent)
               rem = (timespent / percent) * percent_remain
               min = rem / 60
               sec = rem % 60
               try:
                   time_rem = _("%(min)d:%(sec)02d") % {
                   "min": min,
                   "sec": sec,
                   }
               except TypeError:
                   raise TranscoderStatusException(_("Problem calculating time " \
                                              "remaining!"))
               self.ProgressBar.set_text(_("Estimated time remaining: ") + str(time_rem))
               return True
           else:
               self.ProgressBar.set_fraction(0.0)
               return False
       else:
           return False

   # Call gobject.timeout_add with a value of 500millisecond to regularly poll for position so we can
   # use it for the progressbar
   def ProgressBarUpdate(self, source):
       gobject.timeout_add(500, self.Increment_Progressbar)
       # print "ProgressBar timeout_add startet"

   # Use the pygst extension 'discoverer' to get information about the incoming media. Probably need to get codec data in another way.
   # this code is probably more complex than it needs to be currently       
   def succeed(self, d):
       if d.is_video:
           self.videodata = { 'videowidth' : d.videowidth, 'videoheight' : d.videoheight, 
                              'videolenght' : d.videolength }
           self.videoinformation.set_markup(''.join(('<small>', 'Video height&#47;width: ', str(self.videodata['videoheight']), 
                                            "x", str(self.videodata['videowidth']), '</small>')))   
       if d.is_audio:
           self.audiodata = { 'audiochannels' : d.audiochannels, 'samplerate' : d.audiorate }
           self.audioinformation.set_markup(''.join(('<small>', 'Audio channels: ', str(self.audiodata['audiochannels']), '</small>')))

   def discover(self, path):
       def discovered(d, is_media):
           if is_media:
               self.succeed(d)

       d = discoverer.Discoverer(path)
       d.connect('discovered', discovered)
       d.discover()

   def mediacheck(self, FileChosen):
       uri = urlparse (FileChosen)
       path = uri.path
       # print path
       return self.discover(path)

   # Set up function to start listening on the GStreamer bus
   # We need this so we know when the pipeline has started and when the pipeline has stopped
   # listening for ASYNC_DONE is sorta ok way to listen for when the pipeline is running
   # You need to listen on the GStreamer bus to know when EOS is hit for instance.

   def _on_eos(self, source):
       self.ProgressBar.set_text(_("Done Transcoding"))
       context_id = self.StatusBar.get_context_id("EOS")
       self.StatusBar.push(context_id, (_("File saved to ") + self.VideoDirectory))
       self.FileChooser.set_sensitive(True)
       self.containerchoice.set_sensitive(True)
       self.CodecBox.set_sensitive(True)
       self.cancelbutton.set_sensitive(False)
       self.transcodebutton.set_sensitive(False)

   def _start_transcoding(self):
       FileChoice = self.get_widget ("FileChooser").get_uri()
       FileName = self.get_widget ("FileChooser").get_filename()
       containerchoice = self.get_widget ("containerchoice").get_active_text ()
       self._transcoder = transcoder_engine.Transcoder(FileChoice, FileName, containerchoice, self.AudioCodec, self.VideoCodec)
       self._transcoder.connect("ready-for-querying", self.ProgressBarUpdate)
       self._transcoder.connect("got-eos", self._on_eos)
       return True

   def donemessage(self, donemessage, null):
       if donemessage == gst.pbutils.INSTALL_PLUGINS_SUCCESS:
           # print "success " + str(donemessage)
           if gst.update_registry():
               print "Plugin registry updated, trying again"
           else:
               print "GStreamer registry update failed"
           self._start_transcoding()
       elif donemessage == gst.pbutils.INSTALL_PLUGINS_PARTIAL_SUCCESS:
           #print "partial success " + str(donemessage)
           self.check_for_elements()
       elif donemessage == gst.pbutils.INSTALL_PLUGINS_NOT_FOUND:
           # print "not found " + str(donemessage)
           context_id = self.StatusBar.get_context_id("EOS")
           self.StatusBar.push(context_id, _("Plugins not found, choose different codecs."))
           self.FileChooser.set_sensitive(True)
           self.containerchoice.set_sensitive(True)
           self.CodecBox.set_sensitive(True)
           self.cancelbutton.set_sensitive(False)
           self.transcodebutton.set_sensitive(True)
       elif donemessage == gst.pbutils.INSTALL_PLUGINS_USER_ABORT:
           context_id = self.StatusBar.get_context_id("EOS")
           self.StatusBar.push(context_id, _("Codec installation aborted."))
           self.FileChooser.set_sensitive(True)
           self.containerchoice.set_sensitive(True)
           self.CodecBox.set_sensitive(True)
           self.cancelbutton.set_sensitive(False)
           self.transcodebutton.set_sensitive(True)
       else:
           context_id = self.StatusBar.get_context_id("EOS")
           self.StatusBar.push(context_id, _("Missing plugin installation failed: ")) + gst.pbutils.InstallPluginsReturn()

   def check_for_elements(self):
       containerchoice = self.get_widget ("containerchoice").get_active_text ()
       containerstatus = codecfinder.get_muxer_element(codecfinder.containermap[containerchoice])
       audiostatus = codecfinder.get_audio_encoder_element(codecfinder.codecmap[self.AudioCodec])
       videostatus = codecfinder.get_video_encoder_element(codecfinder.codecmap[self.VideoCodec])
       
       if not containerstatus or not videostatus or not audiostatus:
           fail_info = []  
           if containerstatus == False: 
               fail_info.append(gst.caps_from_string(codecfinder.containermap[containerchoice]))
           if audiostatus == False:
               fail_info.append(gst.caps_from_string(codecfinder.codecmap[self.AudioCodec]))
           if videostatus == False:
               fail_info.append(gst.caps_from_string (codecfinder.codecmap[self.VideoCodec]))
           missing = []
           for x in fail_info:
               missing.append(gst.pbutils.missing_encoder_installer_detail_new(x))
           context = gst.pbutils.InstallPluginsContext ()
           gst.pbutils.install_plugins_async (missing, context, self.donemessage, "")
       else:
           self._start_transcoding()

   # The transcodebutton is the one that calls the Transcoder class and thus starts the transcoding
   def on_transcodebutton_clicked(self, widget):
       self.FileChooser.set_sensitive(False)
       self.containerchoice.set_sensitive(False)
       self.CodecBox.set_sensitive(False)
       self.transcodebutton.set_sensitive(False)
       self.cancelbutton.set_sensitive(True)
       self.ProgressBar.set_fraction(0.0)
       self.ProgressBar.set_text(_("Transcoding Progress"))
       self.check_for_elements()

   def on_cancelbutton_clicked(self, widget):
       self.FileChooser.set_sensitive(True)
       self.containerchoice.set_sensitive(True)
       self.CodecBox.set_sensitive(True)
       self.cancelbutton.set_sensitive(False)
       self._cancel_encoding = transcoder_engine.Transcoder.Pipeline(self._transcoder,"null")
       self.ProgressBar.set_fraction(0.0)
       self.ProgressBar.set_text(_("Transcoding Progress"))
       context_id = self.StatusBar.get_context_id("EOS")
       self.StatusBar.pop(context_id)

   # define the behaviour of the other buttons
   def on_FileChooser_file_set(self, widget):
       FileName = self.get_widget ("FileChooser").get_filename()
       codecinfo = self.mediacheck(FileName)
       self.containerchoice.set_sensitive(True)
       self.presetchoice.set_sensitive(True)
       self.presetchoice.set_active(0)
       self.ProgressBar.set_fraction(0.0)
       self.ProgressBar.set_text(_("Transcoding Progress"))

   def on_containerchoice_changed(self, widget):
       self.CodecBox.set_sensitive(True)
       self.transcodebutton.set_sensitive(True)
       self.ProgressBar.set_fraction(0.0)
       self.ProgressBar.set_text(_("Transcoding Progress"))
       containerchoice = self.get_widget ("containerchoice").get_active_text ()
       if containerchoice == "Ogg":
           self.codec_buttons['vorbis'].set_sensitive(True)
           self.codec_buttons['flac'].set_sensitive(True)
           self.codec_buttons['mp3'].set_sensitive(False)
           self.codec_buttons['aac'].set_sensitive(False)
           self.codec_buttons['ac3'].set_sensitive(False)
           self.codec_buttons['speex'].set_sensitive(True)
           self.codec_buttons['celt'].set_sensitive(True)
           self.codec_buttons['theora'].set_sensitive(True)
           self.codec_buttons['dirac'].set_sensitive(True)
           self.codec_buttons['h264'].set_sensitive(False)
           self.codec_buttons['mpeg2'].set_sensitive(False)
           self.codec_buttons['mpeg4'].set_sensitive(False)
           self.codec_buttons['xvid'].set_sensitive(False)
           self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['vorbis'].set_active(True)
           self.codec_buttons['theora'].set_active(True)
       if containerchoice == "MXF":
           self.codec_buttons['vorbis'].set_sensitive(False)
           self.codec_buttons['flac'].set_sensitive(False)
           self.codec_buttons['mp3'].set_sensitive(True)
           self.codec_buttons['aac'].set_sensitive(True)
           self.codec_buttons['ac3'].set_sensitive(True)
           self.codec_buttons['speex'].set_sensitive(False)
           self.codec_buttons['celt'].set_sensitive(False)
           self.codec_buttons['theora'].set_sensitive(False)
           self.codec_buttons['dirac'].set_sensitive(False)
           self.codec_buttons['h264'].set_sensitive(True)
           self.codec_buttons['mpeg2'].set_sensitive(True)
           self.codec_buttons['mpeg4'].set_sensitive(True)
           self.codec_buttons['xvid'].set_sensitive(False)
           self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['mp3'].set_active(True)
           self.codec_buttons['dirac'].set_active(True)
           self.AudioCodec = "mp3"
           self.VideoCodec = "dirac"
       elif containerchoice == "Matroska":
           self.codec_buttons['vorbis'].set_sensitive(True)
           self.codec_buttons['flac'].set_sensitive(True)
           self.codec_buttons['mp3'].set_sensitive(True)
           self.codec_buttons['aac'].set_sensitive(True)
           self.codec_buttons['ac3'].set_sensitive(True)
           self.codec_buttons['speex'].set_sensitive(False)
           self.codec_buttons['celt'].set_sensitive(False)
           self.codec_buttons['theora'].set_sensitive(True)
           self.codec_buttons['dirac'].set_sensitive(True)
           self.codec_buttons['h264'].set_sensitive(True)
           self.codec_buttons['mpeg2'].set_sensitive(True)
           self.codec_buttons['mpeg4'].set_sensitive(True)	
           self.codec_buttons['xvid'].set_sensitive(True)	
           self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['flac'].set_active(True)
           self.AudioCodec = "flac"
           self.codec_buttons['dirac'].set_active(True)
           self.VideoCodec = "dirac"
       elif containerchoice == "AVI":
           self.vorbisbutton.set_sensitive(False)
           self.flacbutton.set_sensitive(False)
           self.mp3button.set_sensitive(True)
           self.aacbutton.set_sensitive(False)
           self.ac3button.set_sensitive(True)
           self.speexbutton.set_sensitive(False)
           self.celtbutton.set_sensitive(False)
           self.theorabutton.set_sensitive(False)
           self.diracbutton.set_sensitive(True)
           self.h264button.set_sensitive(True)
           self.mpeg2button.set_sensitive(True)
           self.mpeg4button.set_sensitive(True)
           self.xvidbutton.set_sensitive(True)
           self.dnxhdbutton.set_sensitive(False)
           self.codec_buttons['mp3'].set_active(True)
           self.AudioCodec = "mp3"
           self.codec_buttons['h264'].set_active(True)
           self.VideoCodec = "h264"
       elif containerchoice == "Quicktime":
           self.codec_buttons['vorbis'].set_sensitive(False)
           self.codec_buttons['flac'].set_sensitive(False)
           self.codec_buttons['mp3'].set_sensitive(True)
           self.codec_buttons['aac'].set_sensitive(True)
           self.codec_buttons['ac3'].set_sensitive(True)
           self.codec_buttons['speex'].set_sensitive(False)
           self.codec_buttons['celt'].set_sensitive(False)
           self.codec_buttons['theora'].set_sensitive(False)
           self.codec_buttons['dirac'].set_sensitive(True)
           self.codec_buttons['h264'].set_sensitive(True)
           self.codec_buttons['mpeg2'].set_sensitive(True)
           self.codec_buttons['mpeg4'].set_sensitive(True)
           self.codec_buttons['xvid'].set_sensitive(False)
           self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['aac'].set_active(True)
           self.AudioCodec = "aac"
           self.codec_buttons['h264'].set_active(True)
           self.VideoCodec = "h264"
       elif containerchoice == "MPEG4":
           self.codec_buttons['vorbis'].set_sensitive(False)
           self.codec_buttons['flac'].set_sensitive(False)
           self.codec_buttons['mp3'].set_sensitive(True)
           self.codec_buttons['aac'].set_sensitive(True)
           self.codec_buttons['ac3'].set_sensitive(False)
           self.codec_buttons['speex'].set_sensitive(False)
           self.codec_buttons['celt'].set_sensitive(False)
           self.codec_buttons['theora'].set_sensitive(False)
           self.codec_buttons['dirac'].set_sensitive(False)
           self.codec_buttons['h264'].set_sensitive(True)
           self.codec_buttons['mpeg2'].set_sensitive(True)
           self.codec_buttons['mpeg4'].set_sensitive(True)
           self.codec_buttons['xvid'].set_sensitive(False)
           self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['aac'].set_active(True)
           self.AudioCodec = "aac"
           self.codec_buttons['h264'].set_active(True)
           self.VideoCodec = "h264"
       elif containerchoice == "3GPP":
           self.codec_buttons['vorbis'].set_sensitive(False)
           self.codec_buttons['flac'].set_sensitive(False)
           self.codec_buttons['mp3'].set_sensitive(True)
           self.codec_buttons['aac'].set_sensitive(True)
           self.codec_buttons['ac3'].set_sensitive(False)
           self.codec_buttons['speex'].set_sensitive(False)
           self.codec_buttons['celt'].set_sensitive(False)
           self.codec_buttons['theora'].set_sensitive(False)
           self.codec_buttons['dirac'].set_sensitive(False)
           self.codec_buttons['h264'].set_sensitive(True)
           self.codec_buttons['mpeg2'].set_sensitive(True)
           self.codec_buttons['mpeg4'].set_sensitive(True)
           self.codec_buttons['xvid'].set_sensitive(False)
           self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['aac'].set_active(True)
           self.AudioCodec = "mp3"
           self.codec_buttons['h264'].set_active(True)
           self.VideoCodec = "h264"
       elif containerchoice == "MPEG PS":
           self.codec_buttons['vorbis'].set_sensitive(False)
           self.codec_buttons['flac'].set_sensitive(False)
           self.codec_buttons['mp3'].set_sensitive(True)
           self.codec_buttons['aac'].set_sensitive(True)
           self.codec_buttons['ac3'].set_sensitive(True)
           self.codec_buttons['speex'].set_sensitive(False)
           self.codec_buttons['celt'].set_sensitive(False)
           self.codec_buttons['theora'].set_sensitive(False)
           self.codec_buttons['dirac'].set_sensitive(False)
           self.codec_buttons['h264'].set_sensitive(True)
           self.codec_buttons['mpeg2'].set_sensitive(True)
           self.codec_buttons['mpeg4'].set_sensitive(True)
           self.codec_buttons['xvid'].set_sensitive(False)
           self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['mp3'].set_active(True)
           self.AudioCodec = "mp3"
           self.codec_buttons['mpeg2'].set_active(True)
           self.VideoCodec = "mpeg2"	  
       elif containerchoice == "MPEG TS":
           self.codec_buttons['vorbis'].set_sensitive(False)
           self.codec_buttons['flac'].set_sensitive(False)
           self.codec_buttons['mp3'].set_sensitive(True)
           self.codec_buttons['aac'].set_sensitive(True)
           self.codec_buttons['ac3'].set_sensitive(True)
           self.codec_buttons['speex'].set_sensitive(False)
           self.codec_buttons['celt'].set_sensitive(False)
           self.codec_buttons['theora'].set_sensitive(False)
           self.codec_buttons['dirac'].set_sensitive(True)
           self.codec_buttons['h264'].set_sensitive(True)
           self.codec_buttons['mpeg2'].set_sensitive(False)
           self.codec_buttons['mpeg4'].set_sensitive(False)
           self.codec_buttons['xvid'].set_sensitive(False)
          self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['mp3'].set_active(True)
           self.AudioCodec = "mp3"
           self.codec_buttons['mpeg2'].set_active(True)
           self.VideoCodec = "h264"	  
       elif containerchoice == "FLV":
           self.codec_buttons['vorbis'].set_sensitive(False)
           self.codec_buttons['flac'].set_sensitive(False)
           self.codec_buttons['mp3'].set_sensitive(True)
           self.codec_buttons['aac'].set_sensitive(False)
           self.codec_buttons['ac3'].set_sensitive(False)
           self.codec_buttons['speex'].set_sensitive(False)
           self.codec_buttons['celt'].set_sensitive(False)
           self.codec_buttons['theora'].set_sensitive(False)
           self.codec_buttons['dirac'].set_sensitive(False)
           self.codec_buttons['h264'].set_sensitive(True)
           self.codec_buttons['mpeg2'].set_sensitive(False)
           self.codec_buttons['mpeg4'].set_sensitive(False)
           self.codec_buttons['xvid'].set_sensitive(False)
           self.codec_buttons['dnxhd'].set_sensitive(False)
           self.codec_buttons['mp3'].set_active(True)
           self.AudioCodec = "mp3"
           self.codec_button['h264'].set_active(True)
           self.VideoCodec = "h264"

   def on_presetchoice_changed(self, widget):
       presetchoice = self.get_widget ("presetchoice").get_active_text ()
       # items = presets.load("/home/cschalle/.transmageddon/presets/ipod.xml")
       # print items
       if presetchoice == "No Presets":
           self.containerchoice.set_sensitive(True)
       else:
           self.containerchoice.set_sensitive(False)

   def audio_codec_changed (self, audio_codec):
       self.transcodebutton.set_sensitive(True)
       self.AudioCodec = audio_codec

   def video_codec_changed (self, video_codec):
       self.transcodebutton.set_sensitive(True)
       self.VideoCodec = video_codec

   def on_audiobutton_pressed(self, widget, codec):
       self.AudioCodec = codec

   def on_videobutton_pressed(self, widget, codec):
       self.VideoCodec = codec

   def on_about_dialog_activate(self, widget):
       """
           Show the about dialog.
       """
       about.AboutDialog()

if __name__ == "__main__":
        hwg = TransmageddonUI()
        gtk.main()



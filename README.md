Distributed-encoding
====================

A few python scripts to encode videos distributed over multiple machines

Usage
-----

The usage is supposed to be fairly easy, however it isn't documented anywhere
really. To run the server, you run:
> $ python2 server.py

It should then start listening for connections on the port specified in the
sourcecode, default is 13337 (because we're just THAT 1337)

The client is a bit more complicated to operate, yet easy enough to be done by
just anyone (hopefully):
> $ python2 client.py \<host\> \<command\> [parameters]

The host obviously specifies the server's address, I don't think this needs any
further explaination.

There are two possible commands as of now, the first one is "ADD" which adds a
file to the encode queue on the server. This file is either present on the
server or is to be sent to it by the client. The "ADD" command also takes
another argument: the encoding settings. An example execution could look like
this:
> $ python2 client.py my-server.com ADD "my_awesome_video[ABCDEFAB].mkv" "--preset placebo --profile high"

Make sure you put especially the second argument in quotation marks otherwise
the command will be split over the argument array and you don't want that to
happen.

The other command logs onto the server and retrieves a chunk from a video to
encode it. This takes one optional argument: the number of chunks to retrieve
and encode. An example execution could look like this:
> $ python2 client.py my-server.com LGN 10

This would encode 10 chunks at max. The script could terminate earlier,
because there are no chunks left. The following would encode until no chunks are
left and then terminate:
> $ python2 client.py my-server.com LGN


Requirements
------------

The server needs mkvinfo and mkvmerge binaries in the working directory. Because
my own server runs debian and the packages are from 2010 I went through the
trouble to compile static binaries, you can find them here:
http://klaxa.in/mkvtoolnix_5.90-linux-x64.tar.gz

They should work on any 64-bit GNU/Linux system.

The client system needs an executable x264 file in the same directory as the
script. To ensure compatibility I compiled static x264 builds for GNU/Linux x64
and Windows 32-bit (MinGW I'm not sure if this works on just any system, but I'm
confident). You may obtain these from http://klaxa.in/x264 (GNU/Linux x64) 
and http://klaxa.in/x264.exe (Windows MinGW)


How does it work?
-----------------

(This might go a bit further into detail than you actually care.)

The server script takes a file and splits it into smaller files. These files are
ensured to be split at I Frames; they contain exactly N I Frames whereas N is
specified in the server sourcecode as "GOPS". Obviously the video won't split up
perfectly into groups of N GOPs unless you specify N to be 1 or 0 (You shouldn't
specify 0, it might end in a divide-by-zero error), therefore the last GOP is
just split by whatever is left. All these parts are now put into a queue which
is called "unassigned". Once a client connects it gets assigned a chunk, this
chunk is then sent by the server to the client, the client then encodes the
chunk and uploads it to the server. The server checks whether or not it was the
last chunk with the same CRC, that is hopefully stored in the filename. If it
was, it merges all encoded files into a new file. Once files have been assiged
they are moved into the "assigned" queue with a timestamp of their creation. In
the server source the variable "TIMEOUT" specifies after how many seconds a
chunk is considered expired, i.e. encoding took too long to be within reasonable
bounds. These chunks get reassigned upon the next client logon.


Why are you requiring CRCs to be stored in the filename?
--------------------------------------------------------

Because this is how fansubbers release their videos. I have written this code to
re-encode videos from H264 High 10 Profile to H264 High Profile so i can play
them on my tablet with hardware decoding without color artifacs and such shit.

TODO
----

- Threaded uploading of encoded files by client. This way the client can upload
a file and already download the next chunk for uploading.
- Change the server to run on Windows and GNU/Linux instead of just GNU/Linux.

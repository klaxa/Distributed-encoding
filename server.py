#!/usr/bin/python2

###############################
# Distributed encoding server #
###############################


import os
import os.path
import Queue
import re
import socket
import struct
import sys
import threading
import time

PORT = 13337
GOPS = 7
NETWORK_CHUNK = 4096
DEBUG = 6
TIMEOUT = 1800
VERSION = "0.1"
# mah spinlock
queue_lock = False


unassigned = Queue.PriorityQueue()
assigned = Queue.PriorityQueue()
priority = 0
addedCRCs = []


server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', PORT))
server.listen(10)

print "Distributed encoding server version %s running on %s." % (VERSION, sys.platform)

# lock specific functions

def acquire():
	global queue_lock
	while queue_lock:
		time.sleep(0.01)
	queue_lock = True

def release():
	global queue_lock
	queue_lock = False

# misc. functions

def getCRC(string):
	CRCs = re.findall("\[[0-F]{8}\]", string)
	if len(CRCs) == 0:
		return 0
	return CRCs[0].strip("][")

def info(string):
	if DEBUG > 4:
		print "(II)", string

def warn(string):
	if DEBUG > 2:
		print "(WW)", string

def error(string):
	if DEBUG > 0:
		print "(EE)", string

# matroska/x264 functions

def make_chunks(filename):
	chunks = []
	i_frames = []
	os.system("./mkvinfo -s " + re.escape(filename) + "| grep \"track 1\" | grep I\ frame > /tmp/mkvinfo.txt")
	mkvinfo = open("/tmp/mkvinfo.txt", "r")
	line = mkvinfo.readline()
	i_frames_num = 0
	while line != '':
		i_frames_num += 1
		if i_frames_num % GOPS == 0:
			i_frames.append(re.findall("[0-9]{2}\:[0-9]{2}\:[0-9]{2}\.[0-9]{3}", line)[0])
		line = mkvinfo.readline()
	mkvinfo.close()
	timecodes = ""
	if len(i_frames) == 0:
		timecodes = "00:00:00.000"
	for frame in i_frames:
		print frame
		timecodes += "," + frame
	mkvmerge_execute = "./mkvmerge -A -S --no-chapters -M -o split." + re.escape(filename) + " --split timecodes:" + timecodes[1:] + " " + filename
	info("Executing: " + mkvmerge_execute)
	os.system(mkvmerge_execute)
	files = os.listdir(".")
	files.sort()
	for i in files:
		if re.match("^split.", i) and getCRC(i) == getCRC(filename):
			chunks.append(i)
	return chunks
# socket functions

def get(sock, size):
	info("Retrieving " + str(size) + " bytes.")
	ret = ""
	chunk = NETWORK_CHUNK
	while size != 0:
		if size < chunk:
			chunk = size
		temp = sock.recv(chunk)
		size -= len(temp)
		ret += temp
	return ret

def get_into(sock, fd, size):
	info("Retrieving " + str(size) + " bytes and writing to file.")
	chunk = NETWORK_CHUNK
	bytes = size
	start = time.time()
	while size != 0:
		if size < chunk:
			chunk = size
		temp = sock.recv(chunk)
		size -= len(temp)
		fd.write(temp)
	end = time.time()
	bitrate = (bytes / 1024) / (end - start)
	info("Retrieved %d in %ds. (%d kB/s)" % (bytes, int(end - start), bitrate))
	
def get_line(sock):
	info("Retrieving line from socket.")
	line = ""
	char = sock.recv(1)
	while char != '\n':
		line += char
		char = sock.recv(1)
	return line

def send_file(sock, filename):
	size = os.path.getsize(filename)
	info("Sending file %s of size %d" % (filename, size))
	fd = open(filename, "r")
	start = time.time()
	sock.send(struct.pack("!i", size))
	sock.sendall(fd.read())
	fd.close()
	end = time.time()
	bitrate = (size / 1024) / (end - start)
	info("Sent %d in %ds. (%d kB/s)" % (size, int(end - start), bitrate))

# server specific functions

def add(sock):
	filename = get_line(sock)
	info("Adding %s to encoding queue" % filename)
	if getCRC(filename) in addedCRCs:
		sock.send("D")
		info("Duplicate not added.")
		sock.close()
		return
	if os.path.isfile(filename):
		sock.send("Y")
		info("Adding new file...")
	else:
		sock.send("N")
		if get(sock, 1) == "Y":
			info("Retrieving file from client")
			(size,) = struct.unpack("!i", get(sock, 4))
			download = open(filename, "w")
			get_into(sock, download, size)
			download.close()
		else:
			warn("File not found and not received by client.")
			sock.close()
			return
	info("Retrieving encoding options")
	encode = get_line(sock)
	chunks = make_chunks(filename)
	global unassigned
	global priority
	info("Waiting for queue lock to add a file.")
	start = time.time()
	acquire()
	end = time.time()
	info("Waited " + str(end - start) + "s for lock to add a file.")
	start = end
	# critical section
	for chunk in chunks:
		unassigned.put((priority, chunk, encode))
		priority += 1
	if DEBUG > 5:
		info("Sleeping for testing purposes.")
		time.sleep(3)
	release()
	end = time.time()
	info("Added chunks; Released lock after " + str(end - start) + "s after adding a file.")
	sock.send("S")
	sock.close()
	addedCRCs.append(getCRC(filename))

def get_chunk():
	global unassigned 
	global assigned
	info("Waiting for queue lock to retrieve chunk with highest priority.")
	start = time.time()
	acquire()
	end = time.time()
	info("Waited " + str(end - start) + "s for lock to retrieve chunk with highest priority.")
	start = end
	# critical section
	# priority ratings: expired assigned == highest, unassigned == high, non-expired assigned = low
	if not assigned.empty():
		info("There are assigned chunks, checking for highest priority chunks (expired, assigned).")
		(timestamp, filename, encode) = assigned.get()
		if (timestamp - time.time()) > TIMEOUT:
			# found chunk that is old enough
			ret = (filename, encode)
		else:
			# no chunk is old enough
			info("No chunk is old enough")
			if not unassigned.empty():
				info("Assigning highest priority unassigned chunk.")
				(priority, filename, encode) = unassigned.get()
				ret = (filename, encode)
				info("Assigning %s." % filename)
			else:
				info("No unassigned chunks nor expired assigned ones, nothing to encode.")
				ret = ("", "")
	else:
		info("Assigned queue is empty.")
		if not unassigned.empty():
			info("Assiging highest priority unassigned chunk.")
			(priority, filename, encode) = unassigned.get()
			ret = (filename, encode)
			info("Assigning %s." % filename)
		else:
			info("All queues emtpy; nothing to encode.")
			ret = ("", "")
	release()
	end = time.time()
	info("Assigned encode; released lock after " + str(end - start) + "s for assigning encode.")
	return ret

def remove_chunk(chunk):
	global assigned
	tempQueue = Queue.Queue()
	start = time.time()
	info("Waiting for queuelock to remove chunk.")
	acquire()
	end = time.time()
	info("Waited " + str(end - start) + "s for lock to remove chunk.")
	# critical section
	start = end
	while not assigned.empty():
		(timestamp, filename, encode) = assigned.get()
		if not filename in chunk:
			tempQueue.put((timestamp, filename, encode))
	while not tempQueue.empty():
		assigned.put(tempQueue.get())
	release()
	end = time.time()
	info("Released lock after " + str(end - start) + "s after removing chunk.")
	

def is_last(chunk):
	global assigned
	global unassigned
	tempQueue = Queue.Queue()
	last_chunk = True
	CRC = getCRC(chunk)
	start = time.time()
	info("Waiting for queuelock to check for last chunk.")
	acquire()
	end = time.time()
	info("Waited " + str(end - start) + "s for lock to check for last chunk.")
	start = end
	while not assigned.empty():
		(timestamp, filename, encode) = assigned.get()
		if CRC == getCRC(filename):
			last_chunk = False
		tempQueue.put((timestamp, filename, encode))
	while not tempQueue.empty():
		assigned.put(tempQueue.get())
	if last_chunk:
		while not unassigned.empty():
			(priority, filename, encode) = unassigned.get()
			if CRC == getCRC(filename):
				last_chunk = False
			tempQueue.put((priority, filename, encode))
		while not tempQueue.empty():
			unassigned.put(tempQueue.get())
	release()
	end = time.time()
	info("Released lock after " + str(end - start) + "s after checking for last chunk.")
	return last_chunk

def concat(filename):
	original = re.sub(".*split\.", "", re.sub("-[0-9]{3}.mkv", ".mkv", filename))
	files = os.listdir(".")
	files.sort()
	merge_files = ""
	for i in files:
		if re.match("^\[8bit\]\ split.", i) and getCRC(i) == getCRC(filename):
			merge_files += " + " + re.escape(i)
			info("Added %s to merge files." % i)
	mkvmerge_execute = "./mkvmerge -o %s %s" % (re.escape(re.sub("split.", "", re.sub("-[0-9]{3}.mkv", ".mkv", filename))), merge_files[3:])
	info("Executing %s" % mkvmerge_execute)
	os.system(mkvmerge_execute)

def finish(sock):
	filename = get_line(sock)
	(size,) = struct.unpack("!i", get(sock, 4))
	download = open(filename, "w")
	get_into(sock, download, size)
	sock.close()
	remove_chunk(filename)
	if is_last(filename):
		concat(filename)

def assign(sock):
	(filename, encode) = get_chunk()
	if filename != "":
		sock.send("Y")
		acquire()
		assigned.put((time.time(), filename, encode))
		release()
		sock.send(filename + '\n')
		send_file(sock, filename)
		sock.send(encode + '\n')
		sock.close()
	else:
		sock.send("N")
		sock.close()

class WorkerThread(threading.Thread):
	def __init__(self, client):
		threading.Thread.__init__(self)
		self.client = client
	def run(self):
		cmd = get(self.client, 3)
		if cmd == "ADD":
			add(self.client)
		if cmd == "LGN":
			assign(self.client)
		if cmd == "RDY":
			finish(self.client)
		
def main():
	while True:
		(client, address) = server.accept()
		worker = WorkerThread(client)
		worker.start()

main()

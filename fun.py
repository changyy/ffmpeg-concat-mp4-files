# -*- coding: utf-8 -*-
import os
import sys
import signal
import subprocess
import threading
import argparse
parser = argparse.ArgumentParser(description='Use ffmpeg concat mp4 files')
parser.add_argument('--files', metavar='File', nargs='+', type=str, help='Sequence MP4(h.264) file for concatenating')
parser.add_argument('--output', metavar='Output', type=str, help='output file')
parser.add_argument('--m3u', metavar='M3U video list', type=str, help='m3u mp4 list')
parser.add_argument('--tmp', metavar='Working Dir', type=str, help='Working dir')
parser.add_argument('--delete-wget-files', action='store_true', help='delete the wget raw files')
parser.add_argument('--max-concurrent-wget-count', metavar='Max concurrent download jobs', type=int, help='Max concurrent wget count')

class MyWGETMultiThread(threading.Thread):
	def __init__(self, job_id, url, save_file, wget_tmp_list, out_list, semo = None):
		threading.Thread.__init__(self)
		self.job_id = job_id
		self.url = url
		self.save_file = save_file
		self.wget_tmp_list = wget_tmp_list
		self.out_list = out_list
		self.semo = semo
		self.cmd = None
	
	def exit(self):
		if self.cmd:
			self.cmd.kill()

	def run(self):
		print "[Wget] file("+str(self.job_id)+"): ", self.url
		cmd = [
			'wget', 
			'-O' , self.save_file,
			'-q' ,
			self.url
		]
		self.cmd = subprocess.Popen( cmd )
		self.cmd.communicate()

		if os.path.exists(self.save_file):
			self.wget_tmp_list.append(self.save_file)
			if os.stat(self.save_file).st_size > 0:
				self.out_list.append(self.save_file)
				print "\tSave: ", self.save_file

		if self.semo:
			self.semo.release()

def exit_gracefully(signum, frame):
	global current_thread_jobs_skip
	current_thread_jobs_skip = True
	global current_thread_jobs
	for job in current_thread_jobs:
		job.exit()

queueLock = threading.Lock()
current_thread_jobs_skip = False
current_thread_jobs = []
max_thread_semo = None

if __name__ == "__main__":
	files = []
	mp4_tmp = []
	wget_tmp = []
	args = parser.parse_args()
	if args.tmp == None:
		args.tmp = '/tmp'
	if args.output == None:
		args.output = '/tmp/output.mp4'
	if args.max_concurrent_wget_count > 0:
		max_thread_semo = threading.BoundedSemaphore(args.max_concurrent_wget_count)
	else:
		max_thread_semo = threading.BoundedSemaphore(1)
	if args.files and len(args.files):
		i = 1
		for target in args.files:
			if os.path.exists(target) and os.stat(target).st_size > 0:
				print "[Add] file("+str(i)+"): ", target
				i = i + 1
				files.append(target)
	if args.m3u:
		lines = [line.strip() for line in open(args.m3u) if line.strip()[0] != '#' and line.strip() != '']
		i = 1
		for target in lines:
			if target[0:4] == 'http':
				# do thread job
				if max_thread_semo:
					max_thread_semo.acquire()

				if current_thread_jobs_skip:
					break
				job = MyWGETMultiThread(i, target, args.tmp+'/wget_'+str(i).zfill(2)+'_.mp4', wget_tmp, files, max_thread_semo)
				i = i + 1
				current_thread_jobs.append(job)
				job.start()
			else:
				if os.path.exists(target) and os.stat(target).st_size > 0:
					print "[Add] file("+str(i)+"): ", target
					i = i + 1
					files.append(target)

		if current_thread_jobs_skip:
			print "Skip..."
			sys.exit(0)

		if len(current_thread_jobs) > 0:
			signal.signal(signal.SIGINT, exit_gracefully)
			for job in current_thread_jobs:
				job.join()
			if current_thread_jobs_skip:
				print "Skip at waiting finish..."
				sys.exit(0)
			print "[Wget] Done"
			
		# sort the list
		files.sort()

	for f in files:
		target = str(args.tmp) + '/tmp_' + os.path.basename(f)
		# ffmpeg -i f -c copy -bsf:v h264_mp4toannexb -f mpegts '/tmp/tmp_filename'
		cmd = [
			'ffmpeg', 
				'-i', f, 
				'-c', 'copy', 
				'-bsf:v', 'h264_mp4toannexb', 
				'-f', 'mpegts', 
				target
		]
		subprocess.call( cmd )
		mp4_tmp.append(target)

	if len(mp4_tmp) <= 1:
		print "No files:", mp4_tmp
		sys.exit(0)

	concat_list = "|".join(mp4_tmp)
	print
	print "concat raw files: ", concat_list
	print
	# ffmpeg -i "concat:/tmp/tmp1|/tmp/tmp2" -c copy -bsf:a aac_adtstoasc output.mp4
	cmd = [
		'ffmpeg', 
			'-i', 'concat:'+str(concat_list), 
			'-c', 'copy', 
			'-bsf:a', 'aac_adtstoasc',
			args.output ,
	]
	subprocess.call( cmd )

	for f in mp4_tmp:
		if os.path.exists(f):
			print "[Remove] mp4_tmp: ", f
			os.remove(f)
	if args.delete_wget_files:
			for f in wget_tmp:
				if os.path.exists(f):
					print "[Remove] wget_tmp: ", f
					os.remove(f)

	print
	print "result: ", args.output
	print

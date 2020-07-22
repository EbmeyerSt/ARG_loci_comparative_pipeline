#!/usr/local/env python3.7

import sys, os, time, multiprocessing, shutil, subprocess

def download_new(queue):

	#download published assemblies
	url=queue.get()
	if url=='STOP':
		return

	while True:

		#Set target directory
		target_dir=sys.argv[1]

		if not os.path.isfile(target_dir+'/'+os.path.basename(url+'_genomic.fna.gz')):

			try:
			
				download_fa='wget -r -nH --cut-dirs=7 %s -P %s' % \
				(url+'/'+os.path.basename(url+'_genomic.fna.gz'), target_dir)

				subprocess.call(download_fa, shell=True)
				time.sleep(1)
				
				#unzip
				unzip='gunzip %s' % target_dir+'/'+os.path.basename(url+'_genomic.fna.gz')
				subprocess.call(unzip, shell=True)

				#Give permissions
				permission='chmod a+r+w %s' % target_dir+'/'+os.path.basename(url+'_genomic.fna')
				subprocess.call(permission, shell=True)

			except Exception as e:
				print('EXCEPTION: %s' % e)

		
		elif os.path.isfile(target_dir+'/'+os.path.basename(url+'_genomic.fna')):
			print('%s already downloaded!' % url)

		url=queue.get()
		if url=='STOP':
			return

def multiprocess(target_func, processes, *items):
	
	#Create queue from files to process
	#NOTE: just one extra item, files have to be at first position
	queue=multiprocessing.Queue()

	for element in items[0]:
		queue.put(element)

	proc_list=[]
	p=processes

	for i in range(p):
		queue.put('STOP')

	started_procs=0
	for i in range(p):
		started_procs+=1

		if len(items)==1:
			proc_list.append(multiprocessing.Process(target=target_func, args=(queue,)))
		elif len(items)>1:
			proc_list.append(multiprocessing.Process(target=target_func, args=(queue, items[1])))

		proc_list[-1].start()

	finished_procs=0
	for p in proc_list:
		finished_procs+=1
		p.join()
		print(f'{finished_procs} of {started_procs} processes finished...')

def main():

	target_directory=sys.argv[1]
	target_dir=sys.argv[1]
	download_file='wget -P %s ftp://ftp.ncbi.nlm.nih.gov/genomes/genbank/bacteria/assembly_summary.txt' % (target_directory)
	subprocess.call(download_file, shell=True)

	genome_urls=[line.split('\t')[19] for line in open(target_directory+'/assembly_summary.txt', 'r') if not line.startswith('#')]
	
	processes=10
	multiprocess(download_new, processes, genome_urls)


if __name__=='__main__':
	main()

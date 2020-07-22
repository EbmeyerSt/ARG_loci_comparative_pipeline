#!/usr/local/env python3.7

import sys, os, subprocess, shutil

def download_plasmids():

	#Directory to download plasmids to
	target_directory=sys.argv[1]

	#Create novel temporary directory for plasmids
	if not os.path.exists(target_directory.rstrip('/')+'/plasmids_tmp'):
		os.mkdir(target_directory.rstrip('/')+'/plasmids_tmp')

	print('downloading new plasmid sequences...')
	download_file2='wget -r -P %s -nd -A .genomic.fna.gz ftp://ftp.ncbi.nlm.nih.gov/refseq/release/plasmid/' \
	% (target_directory.rstrip('/')+'/plasmids_tmp')
	subprocess.call(download_file2, shell=True)

	#Unzip 
	unzip='gunzip %s*' % (target_directory.rstrip('/')+'/plasmids_tmp/')
	subprocess.call(unzip, shell=True)

	print('Reading plasmids to dict...')
	#Read into dict
	plasmid_dict={}
	for file in os.listdir(target_directory.rstrip('/')+'/plasmids_tmp'):
		for line in open(target_directory.rstrip('/')+'/plasmids_tmp/'+file, 'r'):
			if line.startswith('>'):
				header=line
				seq=''
			else:
				seq+=line
				plasmid_dict[header]=seq
	

	print('Writing plasmid summary file...')
	with open(target_directory.rstrip('/')+'/plasmid_summary.txt', 'w') as outfile:
		for key, value in plasmid_dict.items():
			outfile.write(str(key.split(' ')[0].lstrip('>'))+'\t'+' '.join(key.split(' ')[1:3])+'\n')

	#Now write all plasmid accessions to individual files
	print('writing novel plasmids to file...')
	for key, value in plasmid_dict.items():
		with open(target_directory.rstrip('/')\
		+'/'+key.split(' ')[0].lstrip('>')+'_genomic.fna', 'w') as outfile:
			outfile.write(key+value)

	#Remove plasmids_tmp
	shutil.rmtree(target_directory.rstrip('/')+'/plasmids_tmp')

if __name__=='__main__':
	download_plasmids()

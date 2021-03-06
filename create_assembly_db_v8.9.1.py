#!/usr/local/env python3.7

import pandas as pd
import numpy as np
from Bio import SeqIO
from shutil import copyfile
import os, sys, argparse, subprocess, multiprocessing, re, time, json, shutil, sqlite3
from argparse import RawTextHelpFormatter
from multiprocessing import Manager
from collections import defaultdict

#Define arguments for the script, such as input files aso.
def parse_arguments():
	man_description='%r\n\nCreates a database in .json format of genomes with annotation of a chosen set of genes including the specific gene sequences, upstream and downstream regions. Database is created in json format.\n%r' % ('_'*80, '_'*80)
	parser=argparse.ArgumentParser(description=man_description.replace("'", ""), formatter_class=RawTextHelpFormatter)
	parser.add_argument('-d', '--target_directory', help='full(!) path to folder containing a folder for each assembly to be processed', required=True)
	parser.add_argument('-db', '--database', help='database in diamond format containing genes to be annotated', required=True)
	parser.add_argument('-p', '--processes', help='of cores to run the script on', type=int, default=multiprocessing.cpu_count())
	parser.add_argument('-id', '--identity', help='identity cutoff for hits to be saved to the database', type=float, default=90)
	parser.add_argument('--erase', help='erase results of previous analysis and create new ones', action='store_true')
	parser.add_argument('-scov', '--subject_coverage', help='minimum coverage for a hit to be saved to db', type=float, default=90)
	parser.add_argument('-env', '--env_db', help='database to annotate genetic environment', required=True)
	parser.add_argument('-split', help='number of files to obtain for processing flanking regions', required=True, type=int)
	parser.add_argument('--is_db', help='database containing IS, integrons, ISCR', required=True)
	parser.add_argument('--update', help='update', action='store_true')
	args=parser.parse_args()

	return args



def split_fasta(split_num):

	if args.update==True:
		#Split concatenated fasta file into several smaller ones
		file=args.target_directory.rstrip('/')+'/'+'update_tmp/all_assemblies.fna'
		target_dir=args.target_directory.rstrip('/')+'/'+'update_tmp'
	else:
		file=args.target_directory.rstrip('/')+'/all_assemblies.fna'
		target_dir=args.target_directory.rstrip('/')
		split_num=args.split

	line_num=0
	for line in open(file, 'r'):
		line_num+=1

	print('%d lines' % line_num)
	multiplicator=1
	iterated_lines=0

	for line in open(file, 'r'):
		iterated_lines+=1

		if line.startswith('>'):
			previous_complete=True
		else:
			previous_complete=False

		if iterated_lines==1:
			outfile=open(target_dir+'/all_assemblies_'+str(multiplicator)+'.fna', 'w')

		if iterated_lines<=(line_num/split_num)*multiplicator:	
			outfile.write(line)

		elif iterated_lines>=(line_num/split_num)*multiplicator and previous_complete==False:
			outfile.write(line)
		else:
			multiplicator+=1
			outfile=open(target_dir+'/all_assemblies_'+str(multiplicator)+'.fna', 'w')
			outfile.write(line)

def concatenate_and_split():

	if args.update==True:
		target_dict=args.target_directory.rstrip('/')+'/'+'update_tmp'
	else:
		target_dict=args.target_directory.rstrip('/')

	if not os.path.isfile(target_dict.rstrip('/')+'/all_assemblies.fna'):
		print('Concatenating novel assemblies...')
		#Collect new genome fasta files
		new_genomes=[content[0].rstrip('/')+'/'+element for content \
		in os.walk(target_dict) \
		for element in content[2] if element.endswith('_genomic.fna')]

		#Write content of all fasta files to one file, append assembly name to respective contig
		with open(target_dict+'/all_assemblies.fna', 'w') as outfile:
			for file in new_genomes:
				for line in open(file, 'r'):
					if line.startswith('>'):
						outfile.write(line.rstrip('\n')+'__'+\
						file.split('/')[-1].split('_')[0]+'_'+\
						file.split('/')[-1].split('_')[1]+'\n')
					else:
						outfile.write(line)
				outfile.write('\n')
	
	
	#Determine number of split files 
	if args.update==True:
		split_files=[file for file in os.listdir(args.target_directory) if file.startswith('all_assemblies_') \
		and file.endswith('.csv') and len(file.split('.'))==2]
		split_num=len(split_files)

	else:
		split_num=args.split

	#Split fasta file into smaller files
	print('Splitting into %d files...' % split_num)
	split_fasta(split_num)

	#Create .csv version of each file
	#Get list of all target files
	fna_files=[target_dict+'/'+file \
	for file in os.listdir(target_dict)\
	 if file.endswith('.fna') and file.startswith('all_assemblies_')]

	#Multiprocess
	p=10
	multiprocess(convert_fa_to_csv, p, fna_files)
	print('All files converted to .csv')


	

def merge_files():

	#Create a dictionaruy of matching files, so that they can be merged
	file_dict={}
	for filename in os.listdir(args.target_directory.rstrip('/')+'/update_tmp'):
		file_dict[args.target_directory.rstrip('/')+'/update_tmp/'+filename]=''
	
		if os.path.isfile(filename.replace('/update_tmp', '')):
			file_dict[args.target_directory.rstrip('/')+'/update_tmp/'+filename]=\
			args.target_directory.rstrip('/')+'/'+filename

	#now merge files into database directory
	for key, value in file_dict.items():
		if not value=='':
			merge_command='cat %s >> %s' % (key, value)
			subprocess.call(merge_command, shell=True)

	#Delete temporary directory
	shutil.rmtree(args.target_directory.rstrip('/')+'/update_tmp')
	print('''Old and new files merged, temporary update directory removed!\n
	Database was updated!''')

def convert_fa_to_csv(queue):

	fa_file=queue.get()
	if fa_file=='STOP':
		return

	while True:

		#Read seqs into dict
		print('Reading in %s...' % fa_file)
		seq_dict={}

		for line in open(fa_file, 'r'):
			if line.startswith('>'):
				header=line.rstrip('\n')
				seq=''
			else:
				seq+=line.rstrip('\n')
				seq_dict[header]=seq
		
		print('Writing %s to .csv...' % fa_file)
		#write to .csv format
		with open(fa_file.replace('.fna', '.csv'), 'w') as outfile:
			for key, value in seq_dict.items():
				outfile.write(key+'\t'+value+'\n')

		seq_dict.clear()

		#Grab next file from the queue
		fa_file=queue.get()
		if fa_file=='STOP':
			return


#Annotate sequences. Queue is a list like object containing 'tasks' (in this case assembly names) for each process to grab, emptying the queue in the process
def annotate(queue):

	#Grab an item from the queue. If item is 'STOP', end the process
	fa_file=queue.get()
	if fa_file=='STOP':
		return

	ending=fa_file.split('.')[-1]
	while True:
		try:
			if not os.path.exists(fa_file.replace(ending, '_annotated.csv')):
				print('Annotating %s...' % os.path.basename(fa_file))
				#Use diamond to annotate genes with custom thresholds. Accept only one hit per target
				diamond_blast='diamond blastx -p 30 -d %s -q %s -o %s --id %r --more-sensitive --quiet --top 100 --masking 0 --subject-cover %r -f 6 qseqid sseqid stitle pident qstart qend qlen slen length score qseq qframe qtitle' %\
				(args.database, fa_file, fa_file.replace(ending, '_annotated.csv'), args.identity, args.subject_coverage)
				subprocess.call(diamond_blast, shell=True)

				#Sort by queryID and start position

				dmnd_rawout=pd.read_csv(fa_file.replace(ending, '_annotated.csv'), sep='\t', \
				names=['qseqid', 'sseqid', 'stitle', 'pident', 'qstart', 'qend', 'qlen', 'slen', 'length', 'score', 'qseq', 'qframe', 'qtitle'])
				dmnd_rawout.sort_values(by=['qseqid', 'qstart']).to_csv(fa_file.replace(ending, '_annotated.csv'), sep='\t', \
				index=False, header=False)
				#Assign same start and end position if several gene variants hit the same locus to be able to group by exact position and filter best hit
				with open(fa_file.replace(ending, '_annotated_rep.csv'), 'w') as rawout:
					line_number=0
					for line in open(fa_file.replace(ending, '_annotated.csv'), 'r'):
						line_number+=1
						if line_number==1:
							if not line.split('\t')[-2].startswith('-'):
								qseqid=line.split('\t')[0]
								seqstart=line.split('\t')[4]
								seqend=line.split('\t')[5]
								rawout.write(line)
							else: 

								qseqid=line.split('\t')[0]
								seqstart=line.split('\t')[5]
								seqend=line.split('\t')[4]
								rawout.write(line)
						
						else:	#Do this one time for forward, another time for reverse strand (for reverse strand, switch seqstart and seqend)
							if not line.split('\t')[-2].startswith('-'):
								if line.split('\t')[0]==qseqid:
									if int(line.split('\t')[4]) in range(int(seqstart)-100, int(seqstart)+100) and int(line.split('\t')[5]) in range(int(seqend)-100, int(seqend)+100):
										newline=line.split('\t')
										newline[4]=seqstart
										newline[5]=seqend
										rawout.write('\t'.join(newline))
									else:

										seqstart=line.split('\t')[4]
										seqend=line.split('\t')[5]
										rawout.write(line)
								else:

									qseqid=line.split('\t')[0]
									seqstart=line.split('\t')[4]
									seqend=line.split('\t')[5]
									rawout.write(line)
							else:

								if line.split('\t')[0]==qseqid:
									if int(line.split('\t')[5]) in range(int(seqstart)-100, int(seqstart)+100) and int(line.split('\t')[4]) in range(int(seqend)-100, int(seqend)+100):
										newline=line.split('\t')
										newline[5]=seqstart
										newline[4]=seqend
										rawout.write('\t'.join(newline))
									else:

										seqstart=line.split('\t')[5]
										seqend=line.split('\t')[4]
										rawout.write(line)
								else:

									qseqid=line.split('\t')[0]
									seqstart=line.split('\t')[5]
									seqend=line.split('\t')[4]
									rawout.write(line)


				#Select best hit
				dmnd_hits=pd.read_csv(fa_file.replace(ending, '_annotated_rep.csv'), sep='\t', names=['qseqid', 'sseqid', 'stitle', 'pident', 'qstart', 'qend', 'qlen', 'slen', 'length', 'score', 'qseq', 'qframe', 'qtitle'])
				best_hits=dmnd_hits.loc[dmnd_hits.groupby(['qseqid', 'qstart', 'qend'])['score'].idxmax()]
				best_hits.to_csv(fa_file.replace(ending, '_annotated.csv'), sep='\t', index=False, header=False)

					
		except Exception as e:
			print('EXCEPTION: %s, line %r' % (e, sys.exc_info()[-1].tb_lineno))
		fa_file=queue.get()
		if fa_file=='STOP':
			return

#Create database, which is a list of dictionaries containing sequence and metainformation about a genome
def create_db(queue):

	#Grab items from queue, which contains paths to assembly directories
	fa_file=queue.get()
	if fa_file=='STOP':
		return
	print('processing %s' % fa_file)

	#Parse assembly summary files for organism information
	print('Reading in assembly summary file...')
	org_dict={}

	#Identify most recent assembly summary file
	summary_files=[args.target_directory.rstrip('/')+'/'+file for file in os.listdir(args.target_directory) \
	if file.startswith('assembly_summary')]

	newest=sorted(summary_files)[-1]

	for line in open(newest, 'r'):
		if not line.startswith('#'):
			org_dict[line.split('\t')[0]]=line.split('\t')[7]

	tax_lines=[line for line in open(newest, 'r') if not line.startswith('#')]

	#Identity most recent plasmid_summary file
	summary_files_plas=[args.target_directory.rstrip('/')+'/'+file for file in os.listdir(args.target_directory) \
	if file.startswith('plasmid_summary')]

	newest_plas=sorted(summary_files_plas)[-1]

	for line in open(newest_plas, 'r'):
		if len(line)>1:
			org_dict[line.split('\t')[0]]=line.split('\t')[1].rstrip('\n')+' plasmid'	

	while True:
		
		ending=fa_file.split('.')[-1]

		#Create set of contig accessions that contain annotated gene
		arg_assemblies={line.split('\t')[0] for line in open(fa_file.replace(ending, '_annotated.csv'), 'r')}

		seq_dict={}
		#Parse genome .csv files
		for line in open(fa_file.replace(ending, 'csv'), 'r'):
			if line.split(' ')[0].lstrip('>') in arg_assemblies:

				#Create a dictionary containing just the contigs with annotated genes
				seq_dict[line.split(' ')[0].lstrip('>')]=line.split('\t')[1].rstrip('\n')

		#Go through annotated files and extract info
					
		copy_list=[]
		nrows=0
		matches=0
		updated_lines=[]

		#Exclude genomes that have no annotated genes through breaking the
		#loop upon detection of empty annotation file
		if len(open(fa_file.replace(ending, '_annotated.csv'), 'r')
.readlines())<1:
			break
		
		print('Parsing resistance gene annotations...')
		for line in open(fa_file.replace(ending, '_annotated.csv'), 'r'):
			nrows+=1
			gene_name=line.split('\t')[2].split('|')[3].split('[')[0].strip()+'__'+str(nrows)
			card_id_copy=line.split('\t')[1].split('|')[1]+'__'+str(nrows)

		#Extract upstream and downstream contexts of annotated genes. Identify right contig
		#based on diamond output that was saved to the genome

			if line.split('\t')[0] in seq_dict:
				contig_acc=line.split('\t')[0]
				frame=line.split('\t')[11]
				align_start=line.split('\t')[4]
				align_end=line.split('\t')[5]
				genome_acc=line.split('\t')[12].split('__')[-1].rstrip('\n')

				if genome_acc.endswith('.fna'):
					genome_acc=genome_acc.replace('.fna', '.1')

				if frame.startswith('-'):

					#Determine upstr and downstr length for - strand
					down_len=len(seq_dict[contig_acc][:int(align_end)])
					up_len=len(seq_dict[contig_acc][int(align_start):])

					#now extract seqs
					#1.) Both upstream and downstream are longer than 10kb
					if down_len>=10000 and up_len>=10000:
						flanking_seq=\
						seq_dict[contig_acc][int(align_end)-10000:\
						int(align_start)+10000]
						new_uplen=10000
						new_downlen=10000
					#2.) Only upstream is longer than 10kb
					elif down_len<10000 and up_len>=10000:
						flanking_seq=\
						seq_dict[contig_acc][:int(align_start)+10000]
						new_uplen=10000
						new_downlen=down_len
					#3.) Only downstream is longer than 10kb
					elif down_len>=10000 and up_len<10000:
						flanking_seq=\
						seq_dict[contig_acc][int(align_end)-10000:]
						new_uplen=up_len
						new_downlen=10000
					#4.) Both are shorter than 10kb
					else:
						flanking_seq=\
						seq_dict[contig_acc]
						new_uplen=up_len
						new_downlen=down_len

				#Now do the same thing for plus strand seqs
				else:

					#Determine upstr and downstr length for + strand
					down_len=len(seq_dict[contig_acc][int(align_end):])
					up_len=len(seq_dict[contig_acc][:int(align_start)])

					#now extract seqs
					#1.) Both upstream and downstream are longer than 10kb
					if down_len>=10000 and up_len>=10000:
						flanking_seq=\
						seq_dict[contig_acc][int(align_start)-10000:\
						int(align_end)+10000]
						new_uplen=10000
						new_downlen=10000
					#2.) Only upstream is longer than 10kb
					elif down_len<10000 and up_len>=10000:
						flanking_seq=\
						seq_dict[contig_acc][int(align_start)-10000:]
						new_uplen=10000
						new_downlen=down_len
					#3.) Only downstream is longer than 10kb
					elif down_len>=10000 and up_len<10000:
						flanking_seq=\
						seq_dict[contig_acc][:int(align_end)+10000]
						new_uplen=up_len
						new_downlen=10000
					#4.) Both are shorter than 10kb
					else:
						flanking_seq=\
						seq_dict[contig_acc]
						new_uplen=up_len
						new_downlen=down_len

				try:	
					taxon=org_dict[genome_acc]

				except KeyError as e:
					print('Something went wrong when updating an entry - %s' % str(e))

					taxon='unknown'
					for tax_line in tax_lines:
						if genome_acc in tax_line:
							print('Identical assembly found!')
							taxon=org_dict[tax_line.split('\t')[0]]

				

				updated_lines.append(line.replace(line.split('\t')[10], flanking_seq+'\t'+str(new_uplen)+\
				'\t'+str(new_downlen)+'\t'+taxon))	

		#Write all flanking regions to .csv file
		print('Writing flanking regions to file...')
		with open(fa_file+'_flanking_regions.csv', 'w') as outfile:
			for line in updated_lines:
				outfile.write(line)

		#After finishing the current queue item, grab a new one until 'STOP' is encountered
		fa_file=queue.get()
		if fa_file=='STOP':
			return

def erase_previous():

	print('erasing previous results, this could take a while...')
	#Go through all assembly directories and delete the results of previous analyses
	for root, dirs, files in os.walk(args.target_directory):
		for file in os.listdir(root):
			if file.endswith('annotated.csv') or file.endswith('.json') or file.startswith('PROKKA_')\
			or file.endswith('_gene_contigs.fa') or file.endswith('.val')\
			or file=='hypothetical_proteins.fa':
				os.remove(root+'/'+file)
	print('Assembly directories cleaned up!')

		
def run_prodigal(queue):
	
	#Grab items from queue, which contains paths to flanking file files
	fa_file=queue.get()
	if fa_file=='STOP':
		return

	while True:
		
		#Run prodigal
		if not os.path.exists(fa_file.replace('.fna', '_orfs.gff')):
			prodigal_call='prodigal -i %s -a %s -o %s -f gff -p meta' % \
			(fa_file, fa_file.replace('.fna', '_orfs.fna'), fa_file.replace('.fna', '_orfs.gff'))
			subprocess.call(prodigal_call, shell=True)

			#Rewrite headers in _orfs.fna
			orfs={}
			for line in open(fa_file.replace('.fna', '_orfs.fna'), 'r'):
				if line.startswith('>'):
					header=line.split(' ')[0]
					seq=''
				else:
					seq+=line
					orfs[header]=seq

			with open(fa_file.replace('.fna', '_orfs.fna'), 'w') as outfile:
				for key, value in orfs.items():
					outfile.write(key+'\n'+value)


		fa_file=queue.get()
		if fa_file=='STOP':
			return

def cluster_orfs(orf_file, target_dir):

	#Take a file containing all env gene seqs and cluster it. After clustering, create dict as follows:
	if not os.path.isfile(target_dir.rstrip('/')+'/orfs_clustered.fna'):
		cluster_command='cd-hit -T 0 -M 100000 -c 0.95 -s 0.95 -n 5 -i %s -o %s' % (orf_file, \
		target_dir.rstrip('/')+'/orfs_clustered.fna')

		subprocess.call(cluster_command, shell=True)

	#Create dictionary that contains each gene id as key and the representativ ecentroid as value
	clust_dict={}
	clust_lines=[line.rstrip('\n') for line in open(target_dir\
	.rstrip('/')+'/orfs_clustered.fna.clstr', 'r') if not line.startswith('>')]

	for line in clust_lines:
		if line.endswith('*'):
			centroid=line.split('>')[1].split('...')[0]

		clust_dict[line.split('>')[1].split('...')[0]]={}
		clust_dict[line.split('>')[1].split('...')[0]]['centroid']=centroid
	
	return clust_dict


def annotate_orfs(queue):

	fa_file=queue.get()
	if fa_file=='STOP':
		return
	
	while True:

		#Annotate orfs
		if not os.path.exists(fa_file.replace('_orfs.fna', '_orfs_annotated.csv')):
			diamond_call='diamond blastp -p 30 -d %s -q %s -o %s --id 60 --more-sensitive \
			--max-target-seqs 1 --masking 0 --subject-cover 60 -f 6 qseqid sseqid stitle pident \
			qstart qend qlen slen length qframe qtitle' % (args.env_db, fa_file, fa_file.replace('_orfs.fna', '_orfs_annotated.csv'))
			subprocess.call(diamond_call, shell=True)

		#Annotate IS and so on here, with 90% identity
		if not os.path.exists(fa_file.replace('_orfs.fna', '_orfs_ISannotated.csv')):
			IS_call='diamond blastp -p 30 -d %s -q %s -o %s --id 90 --more-sensitive \
			--max-target-seqs 1 --masking 0 --subject-cover 90 -f 6 qseqid sseqid stitle pident \
			qstart qend qlen slen length qframe qtitle' % (args.is_db, fa_file, fa_file.replace('_orfs.fna', '_orfs_ISannotated.csv'))
			subprocess.call(IS_call, shell=True)

		fa_file=queue.get()
		if fa_file=='STOP':
			return

def create_env_dict(all_orfs_gff, all_orf_annos, clust_dict, all_IS_annos):

	#Create list containing all orfs from all flanking regions
	orfs=[line for file in all_orfs_gff for line in open(file, 'r') if not line.startswith('#')]

	#Create list containg all orf annotation information
	anno_orfs=[line for file in all_orf_annos for line in open(file, 'r')]

	#Create list containing all orf annotation information with IS
	anno_orfs_IS=[line for file in all_IS_annos for line in open(file, 'r')]

	#Create dictionary containing orf id and name	
	anno_dict={}
	for line in anno_orfs:
		anno_dict[line.split('\t')[0]]=' '.join(line.split('\t')[1].split('|')[2]\
		.split('_OS=')[0].split('_')[2:])
	
	#Now overwrite these annotations with 'high quality' IS annotations
	for line in anno_orfs_IS:
		anno_dict[line.split('\t')[0]]=line.split('\t')[1].split('|')[3].split(' [')[0]

	#add name key to clust_dict
	print('Assigning names to orfs...')
	for key, value in clust_dict.items():
		try:
			clust_dict[key]['name']=anno_dict[clust_dict[key]['centroid']]
		except:
			clust_dict[key]['name']='hypothetical protein'

	#Create dictionary from all orfs
	env_dict={}
	
	for line in orfs:
		gene_id=line.split('\t')[0]
		env_gene_id=line.split('\t')[8].split(';')[0].split('_')[1]
		new_name=clust_dict[str(gene_id)+'_'+str(env_gene_id)]['name']

		if not gene_id in env_dict:
			env_dict[gene_id]={}

		env_dict[gene_id][env_gene_id]={}
		env_dict[gene_id][env_gene_id]['env_name']=new_name
		env_dict[gene_id][env_gene_id]['env_start']=line.split('\t')[3]
		env_dict[gene_id][env_gene_id]['env_stop']=line.split('\t')[4]
		env_dict[gene_id][env_gene_id]['env_strand']=line.split('\t')[6]

	return env_dict

def annotate_integrons(queue, dir):

	flank_file=queue.get()
	if flank_file=='STOP':
		return

	while True:

		#Run integron finder
		if not os.path.exists(dir.rstrip('/')+'/all_integrons.txt'):
			print('annotating integrons...')
			search_int='integron_finder %s --cpu 30 --quiet --linear --outdir %s' % \
			(flank_file, dir)
			subprocess.call(search_int, shell=True)

			flank_file=queue.get()
			if flank_file=='STOP':
				return

		else:
			print('integron annotations already exist!')
			return

def integrons_to_db():

	if not args.update==True:
		int_folder=args.target_directory.rstrip('/')+'/integrons_tmp/'
	else:
		int_folder=args.target_directory.rstrip('/')+'/update_tmp/integrons_tmp/'

	#Get all integron and summary files from subfolders
	int_files=[root+'/'+file for root, dirs, files in os.walk(int_folder) \
	for file in files if file.endswith('.integrons')]

	sum_files=[root+'/'+file for root, dirs, files in os.walk(int_folder) \
	for file in files if file.endswith('.summary')]

	#summarize results and parse results into dictionary
	with open(int_folder+'all_integrons.txt', 'w') as outfile:
		for file in int_files:
			for line in open(file, 'r'):
				outfile.write(line.rstrip('\n')+'\n')

	with open(int_folder+'all_summaries.txt', 'w') as outfile:
		for file in sum_files:
			for line in open(file, 'r'):
				outfile.write(line.rstrip('\n')+'\n')


	int_lines=[line for line in open(int_folder+'all_integrons.txt', 'r') \
	if not line.startswith('ID') and not line.startswith('#')]

	#Parse results into dictionary
	integron_dict={}
	print('collecting integron data...')
	for line in int_lines:
		gene_acc=line.split('\t')[1]
		int_acc=line.split('\t')[0]
		el_id=line.split('\t')[2]

		if not gene_acc in integron_dict:
			integron_dict[gene_acc]={}
		if not int_acc in integron_dict[gene_acc]:
			integron_dict[gene_acc][int_acc]={}
		integron_dict[gene_acc][int_acc][el_id]={}
		integron_dict[gene_acc][int_acc][el_id]['start']=int(line.split('\t')[3])
		integron_dict[gene_acc][int_acc][el_id]['stop']=int(line.split('\t')[4])
		integron_dict[gene_acc][int_acc][el_id]['name']=line.split('\t')[8]
		integron_dict[gene_acc][int_acc][el_id]['strand']=line.split('\t')[5]

	#Find start and end position of integron, see if complete integron
	for key, value in integron_dict.items():
		for key2, value2 in value.items():
			start_list=[]
			stop_list=[]
			name_list=[]
			for key3, value3 in value2.items():
				start_list.append(value3['start'])
				stop_list.append(value3['stop'])
				name_list.append(value3['name'])
			integron_dict[key][key2]['int_start']=min(start_list)
			integron_dict[key][key2]['int_stop']=max(stop_list)
			if 'attC' in name_list and 'intI' in name_list:
				integron_dict[key][key2]['int_complete']='complete'
			else:
				integron_dict[key][key2]['int_complete']='incomplete'

	#Save results to database
	connection=sqlite3.connect(args.target_directory.rstrip('/')+'/context_db_flank.db')
	cursor=connection.cursor()

	if not args.update==True:
		#Create integron table
		cursor.execute('DROP TABLE IF EXISTS integrons')

		create_table="""
		CREATE TABLE integrons(
		arg_id INTEGER NOT NULL,
		int_id INTEGER NOT NULL PRIMARY KEY,
		int_start INTEGER NOT NULL,
		int_stop INTEGER NOT NULL,
		int_complete VARCHAR(100) NOT NULL,
		FOREIGN KEY (arg_id) REFERENCES args(id) ON DELETE CASCADE
		);
		"""
		cursor.execute(create_table)

		cursor.execute('DROP TABLE IF EXISTS int_elements')

		int_elements="""
		CREATE TABLE int_elements(
		int_id INTEGER NOT NULL,
		el_id INTEGER NOT NULL,
		el_start INTEGER NOT NULL,
		el_stop INTEGER NOT NULL,
		el_name VARCHAR(500),
		el_strand VARCHAR(4),
		FOREIGN KEY (int_id) REFERENCES integrons(int_id) ON DELETE CASCADE
		);
		""" 
		cursor.execute(int_elements)

		#Insert data into tables
		integron_id=0

	else:
		cursor.execute('SELECT MAX(int_id) FROM integrons')
		results=cursor.fetchall()
		integron_id=int(results[0][0])

	for key, value in integron_dict.items():
		for key2, value2 in value.items():
			integron_id+=1
			#into integron table
			cursor.execute('INSERT INTO integrons(arg_id, int_id, int_start, int_stop, \
			int_complete) VALUES(?,?,?,?,?)', (key, integron_id, value2['int_start'], \
			value2['int_stop'], value2['int_complete']))

			for key3, value3 in value2.items():
				if not key3.startswith('int_'):

					if value3['strand'].startswith('-'):
						strand='-'
					else:
						strand='+'

					#into integron element table
					cursor.execute('INSERT INTO int_elements(int_id, el_id, el_start, el_stop, \
					el_name, el_strand) VALUES(?,?,?,?,?,?)', (integron_id, key3, value3['start'], \
					value3['stop'], value3['name'], strand))
	connection.commit()

	print('Integron annotations saved to database!')

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


def to_sql_db(env_dict, all_anno, target_directory):

	#Create a dict containing all neccessary metainfo
	sum_dict={}
	unique_genomes={line.split('\t')[-2].split('__')[-1] for line in open(all_anno, 'r')}

	for genome in unique_genomes:

		if genome.endswith('.fna'):
			genome=genome.replace('.fna', '.1')
		sum_dict[genome]={}
		sum_dict[genome]['annotated genes']={}
	
	for line in open(all_anno, 'r'):

		genome_acc=line.split('\t')[-2].split('__')[-1]
		if genome_acc.endswith('.fna'):
			genome_acc=genome_acc.replace('.fna', '.1')
		prot_id=line.split('\t')[1].split('|')[1]\
		+'__'+line.split('\t')[-1].rstrip('\n')

		sum_dict[genome_acc]['organism']=\
		line.split('\t')[-4]
		sum_dict[genome_acc]['annotated genes'][prot_id]={}
		sum_dict[genome_acc]['annotated genes'][prot_id]['name']=\
		line.split('\t')[1].split('|')[-1]
		sum_dict[genome_acc]['annotated genes'][prot_id]['card_id']=\
		prot_id.split('__')[0]
		sum_dict[genome_acc]['annotated genes'][prot_id]['perc_id']=\
		line.split('\t')[3]
		sum_dict[genome_acc]['annotated genes'][prot_id]['frame']=\
		line.split('\t')[-3]
		sum_dict[genome_acc]['annotated genes'][prot_id]['contig_acc']=\
		line.split('\t')[0]
		sum_dict[genome_acc]['annotated genes'][prot_id]['down_len']=\
		line.split('\t')[-5]
		sum_dict[genome_acc]['annotated genes'][prot_id]['up_len']=\
		line.split('\t')[-6]
		sum_dict[genome_acc]['annotated genes'][prot_id]['aln_len']=\
		int(line.split('\t')[8])*3


	#Create an sql database to save information on flanking genes, seqs etc in. Delete fasta files after
	#Create database file
	connection=sqlite3.connect(target_directory.rstrip('/')+'/context_db_flank.db')

	#Create a cursor to perform sql commands
	cursor=connection.cursor()

	if not args.update==True:
		#Create Tables - drop pre-existing tables
		cursor.execute('DROP TABLE IF EXISTS X')

		create_genomes_table="""
		CREATE TABLE IF NOT EXISTS genomes(
			id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
			assembly VARCHAR(500) UNIQUE NOT NULL,
			organism VARCHAR(500) NOT NULL,
			ncbi_link VARCHAR(500)
			);	
		"""

		cursor.execute(create_genomes_table)

		create_arg_table="""
		CREATE TABLE IF NOT EXISTS args(
			id INTEGER PRIMARY KEY NOT NULL UNIQUE,
			arg_name VARCHAR(100),
			perc_id FLOAT NOT NULL,
			genome_id INTEGER NOT NULL,
			contig_acc VARCHAR(100) NOT NULL,
			arg_len INTEGER NOT NULL,
			uplen INTEGER NOT NULL,
			downlen INTEGER NOT NULL,
			arg_start INTEGER NOT NULL,
			arg_end INTEGER NOT NULL,
			frame INTEGER NOT NULL,
			card_id VARCHAR(100),
			FOREIGN KEY (genome_id) REFERENCES genomes(id) ON DELETE CASCADE
			);
		"""

		cursor.execute(create_arg_table)

		create_env_table="""
		CREATE TABLE IF NOT EXISTS envs(
			id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
			env_name VARCHAR(100) NOT NULL,
			arg_id INTEGER NOT NULL,
			env_start INTEGER NOT NULL,
			env_end INTEGER NOT NULL,
			env_strand VARCHAR(5) NOT NULL,
			FOREIGN KEY (arg_id) REFERENCES args(id) ON DELETE CASCADE
			);
		"""

		cursor.execute(create_env_table)

	#insert data
	if not args.update==True:
		genome_id=0
	else:
		cursor.execute('SELECT MAX(id) FROM genomes')
		results=cursor.fetchall()
		genome_id=int(results[0][0])

	#Insert genomes
	for key, value in sum_dict.items():
		genome_id+=1
		cursor.execute('INSERT INTO genomes(assembly, organism) VALUES(?,?);',\
		 (key, sum_dict[key]['organism']))	

		#Insert annotated genes
		for key2, value2 in value['annotated genes'].items():

			if value2['frame'].startswith('-'):
				strand='-'
			else:
				strand='+'

			cursor.execute('INSERT INTO args(arg_name, genome_id, contig_acc, perc_id, \
			arg_len, frame, card_id, uplen, downlen, arg_start, arg_end, id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?);',\
			(value2['name'], genome_id, value2['contig_acc'], value2['perc_id'], value2['aln_len'],\
			strand, value2['card_id'], value2['up_len'], value2['down_len'], value2['up_len'], int(value2['up_len'])+int(value2['aln_len']),\
			key2.split('__')[-1]))

			try:
				#Insert flanking regions
				for key3, value3 in env_dict[key2.split('__')[-1]].items():
					cursor.execute('INSERT INTO envs(env_name, arg_id, env_start, env_end, env_strand) \
							VALUES(?,?,?,?,?);', (value3['env_name'], key2.split('__')[-1], \
							value3['env_start'], value3['env_stop'], value3['env_strand']))
			except KeyError as e:
				print('No genetic environment found for %s - %s' % (key2, e))
	connection.commit()
	print('Genes and flanking regions saved to DB!')


def main():

	if args.erase==True:
		erase_previous()

	#Determine whether split files are already present
	split_files=[file for file in os.listdir(args.target_directory) if file\
	.startswith('all_assemblies_') and file.endswith('.csv') and len(file.split('.'))==2]

	if not os.path.isfile(args.target_directory.rstrip('/')+'/all_assemblies.fna') \
	or len(split_files)==0:
		concatenate_and_split()	

	print('collecting fasta files for annotation...')
	#Create list of files containing assemblies in fasta format
	fa_files=[args.target_directory.rstrip('/')+'/'+fa_file for fa_file \
	in os.listdir(args.target_directory)\
	if fa_file.startswith('all_assemblies_')\
	and fa_file.endswith('.fna') and not fa_file.startswith('flanking') \
	and not '_orfs' in fa_file]
	
	#Define number of processes and empty list for processes
	multiprocess(annotate, args.processes, fa_files)
	#Do the same again for the 'create_database' function

	#Create list with files that have no corresponding flanking region file yet
	no_flank_files=[element for element in fa_files if not os.path.exists(element+'_flanking_regions.csv')]

	if len(no_flank_files)>0:
		multiprocess(create_db, args.processes, no_flank_files)

	print('collecting flanking regions...')
	flank_files=[args.target_directory.rstrip('/')+'/'+fa_file for fa_file in os.listdir(args.target_directory)\
	if fa_file.startswith('all_assemblies_')\
	and fa_file.endswith('.fna_flanking_regions.csv')]


	#summarize all flanking regions into one temporary file
	lines=[line for file in flank_files for line in open(file, 'r')]

	print('Writing temporary files...')
	with open(args.target_directory.rstrip('/')+'/all_flanks.csv_tmp', 'w') as outfile:
		i=0
		for line in sorted(lines):
			#append ID for identification of env genes
			asm_name=line.split('\t')[-4]
			if asm_name.endswith('.fna'):
				asm_name=asm_name.replace('.fna', '.1')

			i+=1

			#Write in csv format to outfile
			outfile.write(str(i)+'\t'+line.split('\t')[-6]+'\n')

	#after assigning id, split the file into specified number of smaller fasta files again
	outfiles=args.split
	csv_lines=[line for line in open(args.target_directory.rstrip('/')+'/all_flanks.csv_tmp', 'r')]

	line_count=0
	file_count=1
	outfile=open(args.target_directory.rstrip('/')+'/'+\
	'flanking_regions_'+str(file_count)+'.fna', 'w')
	for line in csv_lines:
		line_count+=1
		if line_count<=round((len(csv_lines)/args.split)+0.5, 0):
			outfile.write('>'+line.split('\t')[0]+'\n'+line.split('\t')[-1])
		else:
			file_count+=1
			line_count=0
			outfile=open(args.target_directory.rstrip('/')+'/'+\
			'flanking_regions_'+str(file_count)+'.fna', 'w')
			outfile.write('>'+line.split('\t')[0]+'\n'+line.split('\t')[-1])

	#Create list with flanking regions file paths
	flanking_fa=[args.target_directory.rstrip('/')+'/'+file for file in os.listdir(args.target_directory) \
	if file.startswith('flanking_regions') and file.endswith('.fna') and not '_orfs' in file]

	#Create a multiprocessing queue from the flanking region files
	processes=25
	multiprocess(run_prodigal, processes, flanking_fa)

	#concatenate all orf files into one for clustering
	concat_command='cat %s/flanking_regions_*_orfs.fna > %s/all_orfs.fna' % \
	(args.target_directory.rstrip('/'), args.target_directory.rstrip('/'))
	subprocess.call(concat_command, shell=True)

	#Call clustering function which returns cluster dict
	clust_dict=cluster_orfs(args.target_directory.rstrip('/')+'/all_orfs.fna', \
	args.target_directory)

	#Split resulting centroid file into several for annotation
	print('splitting orf file for annotation...')
	centr_dict={}
	for line in open(args.target_directory.rstrip('/')+'/orfs_clustered.fna'):
		if line.startswith('>'):
			header=line
			seq=''
		else:
			seq+=line
			centr_dict[header]=seq

	outfiles=args.split

	key_count=0
	file_count=1
	outfile=open(args.target_directory.rstrip('/')+'/'+\
	'split_'+str(file_count)+'_orfs.fna', 'w')
	for key, value in centr_dict.items():
		key_count+=1
		if key_count<=round((len(centr_dict)/args.split)+0.5, 0):
			outfile.write(key+value)
		else:
			file_count+=1
			key_count=0
			outfile=open(args.target_directory.rstrip('/')+'/'+\
			'split_'+str(file_count)+'_orfs.fna', 'w')
			outfile.write(key+value)


	#Do the exact same thing for 'annotate_orfs' function
	orf_files=[args.target_directory.rstrip('/')+'/'+file for file in \
	os.listdir(args.target_directory) if file.endswith('_orfs.fna') \
	and file.startswith('split_')]

	multiprocess(annotate_orfs, args.processes, orf_files)

	#Create a temporary summary file containing the line id
	with open(args.target_directory.rstrip('/')+'/all_annos.fna_tmp', 'w') as outfile:
		i=0
		for line in sorted(lines):
			i+=1
			outfile.write(line.rstrip('\n')+'\t'+str(i)+'\n')

	print('summarizing files...')
	all_orfs_gff=[args.target_directory.rstrip('/')+'/'+file for file in os.listdir(args.target_directory) \
	if file.endswith('_orfs.gff')]	

	all_orf_annos=[args.target_directory.rstrip('/')+'/'+file for file in os.listdir(args.target_directory) \
	if file.endswith('_orfs_annotated.csv')]

	all_IS_annos=[args.target_directory.rstrip('/')+'/'+file for file in os.listdir(args.target_directory) \
	if file.endswith('_orfs_ISannotated.csv')]

	print('combining genome features...')
	#Now create a function that creates the env dict!
	env_dict=create_env_dict(all_orfs_gff, all_orf_annos, clust_dict, all_IS_annos)

	to_sql_db(env_dict, args.target_directory.rstrip('/')+'/all_annos.fna_tmp', args.target_directory)


	#run integron finder and integrate into database
	#Create list with flanking region files
	flanks=[args.target_directory.rstrip('/')+'/'+file for file in os.listdir(\
	args.target_directory) if file.startswith('flanking_regions_') and \
	file.endswith('.fna') and not '_orfs' in file]

	#Create temporary directory
	if not os.path.exists(args.target_directory.rstrip('/')+'/integrons_tmp'):
		os.mkdir(args.target_directory.rstrip('/')+'/integrons_tmp')

	dir=args.target_directory.rstrip('/')+'/integrons_tmp'

	multiprocess(annotate_integrons, args.processes, flanks, dir)	
	integrons_to_db()

	#Create arg/tnp association table
	transposon_table()

def transposon_table():

	#Create table that contains args having a transposon 3000kbp upstream/downstream
	#of them and associated transposon annotation
	connection=sqlite3.connect(args.target_directory.rstrip('/')+'/context_db_flank.db')
	cursor=connection.cursor()

	find_tnp_args="""
	SELECT args.id, arg_name, envs.id, env_name FROM args
	INNER JOIN envs ON args.id=envs.arg_id
	WHERE (env_name LIKE 'IS%' OR env_name LIKE '%ranspos%'
	OR env_name LIKE 'insertion sequen%'
	OR env_name LIKE 'ISCR%'
	OR env_name LIKE 'tnp%'
	OR env_name LIKE 'Tnp%')
	AND (env_name NOT LIKE 'Isocho%')
	AND (env_name NOT LIKE 'Istb%')
	AND (env_name NOT LIKE 'Isoleu')
	AND ((env_start>=uplen-4000 AND env_end<=uplen)
	OR (env_start>=uplen+arg_len AND env_end<=uplen+arg_len+4000))
	"""

	#Execute search statement
	cursor.execute(find_tnp_args)
	results=cursor.fetchall()

	cursor.execute('DROP TABLE IF EXISTS arg_tnps')

	#Creae new table from results
	tnp_arg_table="""
	CREATE TABLE IF NOT EXISTS arg_tnps(
	arg_id INTEGER NOT NULL,
	arg_name VARCHAR(100) NOT NULL,
	env_id INTEGER NOT NULL,
	tnp_name VARCHAR(200) NOT NULL,
	FOREIGN KEY (arg_id) REFERENCES args(id)
	FOREIGN KEY (env_id) REFERENCES envs(id)
	);
	"""

	cursor.execute(tnp_arg_table)

	#Insert data into table
	for element in results:
		cursor.execute('INSERT INTO arg_tnps(arg_id, arg_name, env_id, tnp_name) VALUES(?,?,?,?)', \
				(element[0], element[1], element[2], element[3]))

	connection.commit()
	print('Arg/transposon associations saved to db!')



if __name__=='__main__':

	args=parse_arguments()
	main()

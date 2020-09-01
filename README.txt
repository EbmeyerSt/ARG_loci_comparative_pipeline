This file contains usage instructions for the code used in the comaparative genome analysis for manuscript	COMMSBIO-20-1935-T.
Several different scripts (written in python 2.7/3.7) are utilized to in the end generate a visualization of the genetic environments of the selected antibiotic resistance gene.
The scripts need to be run on a UNIX system with python3.7 installed. 

DISCLAIMER: The visualization created by this pipeline is not perfect - ORF predictions and annotations may contain errors. It is therefore strongly advised to manually curate sequences of interest in order to make conclusions about a potential origin of a resistance gene!

NOTE: The size of the whole dataset is considerable - obtaining the results may take several days dependend on 
your computational resources! A smaller test set of genomes containing the FOX AmpC-beta-lactamase can be downloaded using SCRIPT X

USAGE INSTRUCTIONS:
Run the scripts in the following order:

1.) download_assemblies.py and download_plasmids.py will download all available genome assemblies and plasmids (refseq only for plasmids). 
The size of this dataset is roughly 3.3TB at the time of writing.

2.) create_assembly_db_v8.9.1.py is a pipeline that annotates ARGs all genomes and plasmids, extracts their genetic environments, predicts and annotates genes on the environmental sequences,
identifies integrons in the sequences. 
NOTE: This code is being further developed, the --update parameter is truncated in this version and not needed for the current manuscript.
The output of this pipeline is a sqlite3 database. (Type 'python create_assembly_db_v8.9.1.py -h' to view the neccessary parameters, to run script: 
'python /path/to/script/create_assembly_db_v8.9.py -d /path/to/genomes -db /path/to/db/hybrid_card.dmnd -p X -id X -scov X -env path/to/db/uniprotKB_clustered_nohypo_merged_nospace_GN_jan2019.dmnd -split 5 --is_db /path/to/db/is_db.dmnd'

3.) extract_genes_sqlite_v7.4.py extracts the specified genes and information on their genetic environments from the database and other files created through
the above script and creates a directory containing all instances of the gene from different genomes as a fasta file. Run 'python extract_genes_sqlite_v7.4.py -h
for input options. The file to be specified with the -flank parameter, all_flanks.csv, is created during creatio of the sqlite3 database.

4.) visualize_v7.8.py creates alignment, phylogeny and visualization of all genetic environments containing the specific resistance gene. The python package ete3 
needs to be installed in order to run the script

File Descriptions
------------------

hybrid_card.dmnd is a DIAMOND format database containing all resistance genes present in both CARD and ResFinder, with CARD format headers

is_db.dmnd is a DIAMOND format database containing custom collected sequences of transposases, IS and ISCR elements - note that the annotations in this file 
are only used to improve the visualization - in the comparative analysis, sequences are manually searched against ISFinder to identify different IS. NOTE: This file is too large to upload here - it can be provided to the editor upon request

uniprotKB_clustered_nohypo_merged_nospace_GN_jan2019.dmnd is a DIAMOND format database containing a modified form of UniprotKB - Note that this is used only for visualization.(e.g to see whether two loci of the same species are annotated similarily)
The exact identity of environmental genes is confirmed through manual blast analyses in the comparative analysis.NOTE: This file is too large to upload here - it can be provided to the editor upon request



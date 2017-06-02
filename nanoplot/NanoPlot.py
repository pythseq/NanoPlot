#! /usr/bin/env python
# wdecoster
'''
The main purpose of this script is to create plots for nanopore data.
Input data can be given as
-compressed, standard or streamed fastq file
-compressed, standard or streamed fastq file with additional information added by albacore
-a bam file
'''


from __future__ import division, print_function
import argparse
import sys
import os
import time
import logging
import datetime
import re
import seaborn as sns
import pandas as pd
import numpy as np
from multiprocessing import cpu_count
from scipy import stats
import matplotlib.pyplot as plt
import pysam
import nanoget
import nanoplotter
import nanomath
version="0.8.1"


def main():
	'''
	Organization function
	Calls plotting functions with appropriate data
	'''
	if not os.path.exists(args.outdir):
		os.makedirs(args.outdir)
	stamp = initlogs(time.time())
	datadf, lengthprefix, logBool, readlengthsPointer, tamp = getInput(stamp)
	nanoplotter.scatter(
		x=datadf[readlengthsPointer],
		y=datadf["quals"],
		names=['Read lengths', 'Average read quality'],
		path=os.path.join(args.outdir, args.prefix + lengthprefix + "LengthvsQualityScatterPlot"),
		log=logBool)
	stamp = timeStamp(stamp, "Creating LengthvsQual plot")

	if args.fastq or args.fastq_albacore:
		nanoplotter.lengthPlots(
			array=datadf[readlengthsPointer],
			name="Read length",
			path=os.path.join(args.outdir, args.prefix + lengthprefix),
			n50=nanomath.getN50(np.sort(datadf["lengths"])),
			log=logBool)
		stamp = timeStamp(stamp, "Creating length plots")
	if args.fastq_albacore:
		nanoplotter.spatialHeatmap(
			array=datadf["channelIDs"],
			title="Number of reads generated per channel",
			path=os.path.join(args.outdir, args.prefix + "ActivityMap_ReadsPerChannel"),
			colour="Greens")
		stamp = timeStamp(stamp, "Creating spatialheatmap for succesfull basecalls")
		nanoplotter.timePlots(
			df=datadf,
			path=os.path.join(args.outdir, args.prefix))
		stamp = timeStamp(stamp, "Creating timeplots")
	if args.bam:
		bamplots(datadf, lengthprefix, logBool, readlengthsPointer, stamp)
	logging.info("Succesfully processed all input.")


def getInput(stamp):
	'''
	Get input and process accordingly. 	Data can be:
	-a uncompressed, bgzip, bzip2 or gzip compressed fastq file
	-s sorted bam file
	Handle is passed to the proper functions to get DataFrame with metrics
	'''
	if args.fastq:
		datadf = nanoget.processFastq(args.fastq)
	elif args.bam:
		datadf = nanoget.processBam(args.bam, min(cpu_count() - 1, args.threads))
	elif args.fastq_albacore:
		datadf = nanoget.processFastq_albacore(args.fastq_albacore)
	else:
		logging.error("ARGUMENT ERROR: no input presented.")
		sys.exit('''ARGUMENT ERROR: Required argument is either:\n \
					a (compressed) fastq file [--fastq]\n \
					a (compressed) fastq file generated by albacore [--fastq_albacore]\n \
					a sorted bam file [--bam].''')
	stamp = timeStamp(stamp, "Gathering data")
	datadf, lengthprefix, logBool, readlengthsPointer = filterData(datadf)
	return (datadf, lengthprefix, logBool, readlengthsPointer, stamp)


def filterData(datadf):
	'''
	Perform filtering on the data based on arguments set on commandline
	- use alighned length or sequenced length (bam mode only)
	- drop outliers
	- drop reads longer than args.maxlength
	- use log10 scaled reads
	- downsample reads to args.downsample
	Return an accurate prefix which is added to plotnames using this filtered data
	'''
	lengthprefix = []
	if args.alength and args.bam:
		readlengthsPointer = "aligned_lengths"
		lengthprefix.append("Aligned_")
		logging.info("Using aligned read lengths for plotting.")
	else:
		readlengthsPointer = "lengths"
		logging.info("Using sequenced read lengths for plotting.")
	if args.drop_outliers:
		datadf=nanomath.removeLengthOutliers(datadf, readlengthsPointer)
		lengthprefix.append("OutliersRemoved_")
		logging.info("Removing length outliers for plotting.")
	if args.maxlength:
		datadf=datadf[datadf[readlengthsPointer] < args.maxlength]
		lengthprefix.append("MaxLength" + str(args.maxlength) + '_')
		logging.info("Removing reads longer than {}.".format(str(args.maxlength)))
	if args.loglength:
		datadf[readlengthsPointer] = np.log10(datadf[readlengthsPointer])
		lengthprefix.append("Log_")
		logging.info("Using Log10 scaled read lengths.")
		logBool = True
	else:
		logBool = False
	if args.downsample:
		newNum = min(args.downsample, len(datadf.index))
		lengthprefix.append("Downsampled_")
		logging.info("Downsampling the dataset from {} to {} reads".format(len(datadf.index), newNum))
		datadf = datadf.sample(newNum)
	return(datadf, ''.join(lengthprefix), logBool, readlengthsPointer)


def getArgs():
	parser = argparse.ArgumentParser(description="Perform diagnostic plotting, QC analysis Nanopore sequencing data and alignments.")
	out = parser.add_mutually_exclusive_group()
	parser.add_argument("--threads",
						help="Set the allowed number of threads to be used by the script",
						default=4,
						type=int)
	parser.add_argument("--time",
						help="Give timestamps to stderr for optimization purposes",
						action="store_true")
	parser.add_argument("--maxlength",
						help="Drop reads longer than length specified.",
						type=int)
	parser.add_argument("--drop_outliers",
						help="Drop outlier reads with extreme long length.",
						action="store_true")
	parser.add_argument("--downsample",
						help="Reduce dataset to N reads by random sampling.",
						type=int)
	parser.add_argument("--loglength",
						help="Logarithmic scaling of lengths in plots.",
						action="store_true")
	parser.add_argument("--alength",
						help="Use aligned read lengths rather than sequenced length (bam mode)",
						action="store_true")
	parser.add_argument("--outdir",
						help="Specify directory in which output has to be created.",
						default=".")
	parser.add_argument("--version",
						help="Print version and exit.",
						action="store_true")
	parser.add_argument("--prefix",
						help="Specify an optional prefix to be used for the output files.",
						default="",
						type=str)
	target = parser.add_mutually_exclusive_group()
	target.add_argument("--fastq",
						help="Data presented is in fastq format.")
	target.add_argument("--fastq_albacore",
						help="Data presented is in fastq format generated by albacore with additional information concerning channel and time.")
	target.add_argument("--bam",
						help="Data presented as a bam file.")
	args = parser.parse_args()
	if args.version:
		print("Nanoplot {}".format(version))
		sys.exit(0)
	return(args)


def timeStamp(start, task):
	now = time.time()
	if args.time:
		sys.stderr.write(task + " took {0:.2f} seconds\n".format(now - start))
	logging.info("Task {0} took {1:.2f} seconds".format(task, now - start))
	return now


def initlogs(time0):
	try:
		start_time = datetime.datetime.fromtimestamp(time0).strftime('%Y%m%d_%H%M')
		logging.basicConfig(
			format='%(asctime)s %(message)s',
			filename=os.path.join(args.outdir, args.prefix + "Nanoplot_" + start_time + ".log"),
			level=logging.INFO)
	except IOError:
		sys.exit("ERROR: No writing permission to the directory.")
	logging.info('Nanoplot {} started with arguments {}'.format(version, args))
	logging.info("{} cpu's are available".format(cpu_count()))
	logging.info('Versions of key modules are:')
	for module in [np, sns, pd, pysam]:
		logging.info('{}: {}'.format(module, module.__version__))
	return time0


def bamplots(datadf, lengthprefix, logBool, readlengthsPointer, stamp):
	'''Call plotting functions specific for bam files'''
	nanoplotter.lengthPlots(
		array=datadf[readlengthsPointer],
		name="Read length",
		path=os.path.join(args.outdir, args.prefix + lengthprefix),
		n50=nanomath.getN50(np.sort(datadf["lengths"])),
		log=logBool)
	stamp = timeStamp(stamp, "Creating length plots")
	nanoplotter.scatter(
		x=datadf["aligned_lengths"],
		y=datadf["lengths"],
		names=["Aligned read lengths", "Sequenced read length"],
		path=os.path.join(args.outdir, args.prefix + "AlignedReadlengthvsSequencedReadLength"))
	stamp = timeStamp(stamp, "Creating AlignedLengthvsLength plot")
	nanoplotter.scatter(
		x=datadf["mapQ"],
		y=datadf["quals"],
		names=["Read mapping quality", "Average basecall quality"],
		path=os.path.join(args.outdir, args.prefix + "MappingQualityvsAverageBaseQuality"))
	stamp = timeStamp(stamp, "Creating MapQvsBaseQ plot")
	nanoplotter.scatter(
		x=datadf[readlengthsPointer],
		y=datadf["mapQ"],
		names=["Read length", "Read mapping quality"],
		path=os.path.join(args.outdir, args.prefix + lengthprefix + "MappingQualityvsReadLength"),
		log=logBool)
	stamp = timeStamp(stamp, "Creating MapQvsBaseQ plot")
	nanoplotter.scatter(
		x=datadf["percentIdentity"],
		y=datadf["quals"],
		names=["Percent identity", "Read quality"],
		path=os.path.join(args.outdir, args.prefix + "PercentIdentityvsAverageBaseQuality"),
		stat=stats.pearsonr)
	stamp = timeStamp(stamp, "Creating PIDvsBaseQ plot")
	nanoplotter.scatter(
		x=datadf[readlengthsPointer],
		y=datadf["percentIdentity"],
		names=["Aligned read length", "Percent identity"],
		path=os.path.join(args.outdir, args.prefix + "PercentIdentityvsAlignedReadLength"),
		stat=stats.pearsonr,
		log=logBool)
	stamp = timeStamp(stamp, "Creating PIDvsLength plot")


if __name__ == "__main__":
	args = getArgs()
	main()

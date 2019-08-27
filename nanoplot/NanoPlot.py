#! /usr/bin/env python
# wdecoster

'''
The main purpose of this script is to create plots for long read sequencing data.
Input data can be given as one or multiple of:
-compressed, standard or streamed fastq file
-compressed, standard or streamed fastq file, with
 additional information added by albacore or MinKNOW
-a bam file
-a summary file generated by albacore
'''


from os import path
import logging
import nanomath
import numpy as np
from scipy import stats
import nanoplot.utils as utils
from nanoget import get_input
from nanoplot.filteroptions import filter_and_transform_data
import nanoplotter
import pickle
import sys


def main():
    '''
    Organization function
    -setups logging
    -gets inputdata
    -calls plotting function
    '''
    settings, args = utils.get_args()
    try:
        utils.make_output_dir(args.outdir)
        utils.init_logs(args)
        args.format = nanoplotter.check_valid_format(args.format)
        sources = {
            "fastq": args.fastq,
            "bam": args.bam,
            "cram": args.cram,
            "fastq_rich": args.fastq_rich,
            "fastq_minimal": args.fastq_minimal,
            "summary": args.summary,
            "fasta": args.fasta,
            "ubam": args.ubam,
        }

        if args.pickle:
            datadf = pickle.load(open(args.pickle, 'rb'))
        else:
            datadf = get_input(
                source=[n for n, s in sources.items() if s][0],
                files=[f for f in sources.values() if f][0],
                threads=args.threads,
                readtype=args.readtype,
                combine="simple",
                barcoded=args.barcoded)
        if args.store:
            pickle.dump(
                obj=datadf,
                file=open(settings["path"] + "NanoPlot-data.pickle", 'wb'))
        if args.raw:
            datadf.to_csv(settings["path"] + "NanoPlot-data.tsv.gz",
                          sep="\t",
                          index=False,
                          compression="gzip")

        settings["statsfile"] = [make_stats(datadf, settings, suffix="")]
        datadf, settings = filter_and_transform_data(datadf, settings)
        if settings["filtered"]:  # Bool set when filter was applied in filter_and_transform_data()
            settings["statsfile"].append(
                make_stats(datadf[datadf["length_filter"]], settings, suffix="_post_filtering")
            )

        if args.barcoded:
            barcodes = list(datadf["barcode"].unique())
            plots = []
            for barc in barcodes:
                logging.info("Processing {}".format(barc))
                settings["path"] = path.join(args.outdir, args.prefix + barc + "_")
                dfbarc = datadf[datadf["barcode"] == barc]
                if len(dfbarc) > 5:
                    settings["title"] = barc
                    plots.extend(
                        make_plots(dfbarc, settings)
                    )
                else:
                    sys.stderr.write("Found barcode {} less than 5x, ignoring...\n".format(barc))
                    logging.info("Found barcode {} less than 5 times, ignoring".format(barc))
        else:
            plots = make_plots(datadf, settings)
        make_report(plots, settings)
        logging.info("Finished!")
    except Exception as e:
        logging.error(e, exc_info=True)
        print("\n\n\nIf you read this then NanoPlot has crashed :-(")
        print("Please try updating NanoPlot and see if that helps...\n")
        print("If not, please report this issue at https://github.com/wdecoster/NanoPlot/issues")
        print("If you could include the log file that would be really helpful.")
        print("Thanks!\n\n\n")
        raise


def make_stats(datadf, settings, suffix):
    statsfile = settings["path"] + "NanoStats" + suffix + ".txt"
    nanomath.write_stats(
        datadfs=[datadf],
        outputfile=statsfile)
    logging.info("Calculated statistics")
    if settings["barcoded"]:
        barcodes = list(datadf["barcode"].unique())
        statsfile = settings["path"] + "NanoStats_barcoded.txt"
        nanomath.write_stats(
            datadfs=[datadf[datadf["barcode"] == b] for b in barcodes],
            outputfile=statsfile,
            names=barcodes)
    return statsfile


def make_plots(datadf, settings):
    '''
    Call plotting functions from nanoplotter
    settings["lengths_pointer"] is a column in the DataFrame specifying which lengths to use
    '''
    plot_settings = dict(font_scale=settings["font_scale"])
    nanoplotter.plot_settings(plot_settings, dpi=settings["dpi"])
    color = nanoplotter.check_valid_color(settings["color"])
    colormap = nanoplotter.check_valid_colormap(settings["colormap"])
    plotdict = {type: settings["plots"].count(type) for type in ["kde", "hex", "dot", 'pauvre']}
    plots = []
    if settings["N50"]:
        n50 = nanomath.get_N50(np.sort(datadf["lengths"]))
    else:
        n50 = None
    plots.extend(
        nanoplotter.length_plots(
            array=datadf[datadf["length_filter"]]["lengths"].astype('uint64'),
            name="Read length",
            path=settings["path"],
            n50=n50,
            color=color,
            figformat=settings["format"],
            title=settings["title"])
    )
    logging.info("Created length plots")
    if "quals" in datadf:
        plots.extend(
            nanoplotter.scatter(
                x=datadf[datadf["length_filter"]][settings["lengths_pointer"]],
                y=datadf[datadf["length_filter"]]["quals"],
                names=['Read lengths', 'Average read quality'],
                path=settings["path"] + "LengthvsQualityScatterPlot",
                color=color,
                figformat=settings["format"],
                plots=plotdict,
                log=settings["logBool"],
                title=settings["title"],
                plot_settings=plot_settings)
        )
        logging.info("Created LengthvsQual plot")
    if "channelIDs" in datadf:
        plots.extend(
            nanoplotter.spatial_heatmap(
                array=datadf["channelIDs"],
                title=settings["title"],
                path=settings["path"] + "ActivityMap_ReadsPerChannel",
                color=colormap,
                figformat=settings["format"])
        )
        logging.info("Created spatialheatmap for succesfull basecalls.")
    if "start_time" in datadf:
        plots.extend(
            nanoplotter.time_plots(
                df=datadf,
                path=settings["path"],
                color=color,
                figformat=settings["format"],
                title=settings["title"],
                log_length=settings["logBool"],
                plot_settings=plot_settings)
        )
        logging.info("Created timeplots.")
    if "aligned_lengths" in datadf and "lengths" in datadf:
        plots.extend(
            nanoplotter.scatter(
                x=datadf[datadf["length_filter"]]["aligned_lengths"],
                y=datadf[datadf["length_filter"]]["lengths"],
                names=["Aligned read lengths", "Sequenced read length"],
                path=settings["path"] + "AlignedReadlengthvsSequencedReadLength",
                figformat=settings["format"],
                plots=plotdict,
                color=color,
                title=settings["title"],
                plot_settings=plot_settings)
        )
        logging.info("Created AlignedLength vs Length plot.")
    if "mapQ" in datadf and "quals" in datadf:
        plots.extend(
            nanoplotter.scatter(
                x=datadf["mapQ"],
                y=datadf["quals"],
                names=["Read mapping quality", "Average basecall quality"],
                path=settings["path"] + "MappingQualityvsAverageBaseQuality",
                color=color,
                figformat=settings["format"],
                plots=plotdict,
                title=settings["title"],
                plot_settings=plot_settings)
        )
        logging.info("Created MapQvsBaseQ plot.")
        plots.extend(
            nanoplotter.scatter(
                x=datadf[datadf["length_filter"]][settings["lengths_pointer"]],
                y=datadf[datadf["length_filter"]]["mapQ"],
                names=["Read length", "Read mapping quality"],
                path=settings["path"] + "MappingQualityvsReadLength",
                color=color,
                figformat=settings["format"],
                plots=plotdict,
                log=settings["logBool"],
                title=settings["title"],
                plot_settings=plot_settings)
        )
        logging.info("Created Mapping quality vs read length plot.")
    if "percentIdentity" in datadf:
        minPID = np.percentile(datadf["percentIdentity"], 1)
        if "aligned_quals" in datadf:
            plots.extend(
                nanoplotter.scatter(
                    x=datadf["percentIdentity"],
                    y=datadf["aligned_quals"],
                    names=["Percent identity", "Average Base Quality"],
                    path=settings["path"] + "PercentIdentityvsAverageBaseQuality",
                    color=color,
                    figformat=settings["format"],
                    plots=plotdict,
                    stat=stats.pearsonr if not settings["hide_stats"] else None,
                    minvalx=minPID,
                    title=settings["title"],
                    plot_settings=plot_settings)
            )
            logging.info("Created Percent ID vs Base quality plot.")
        plots.extend(
            nanoplotter.scatter(
                x=datadf[datadf["length_filter"]][settings["lengths_pointer"]],
                y=datadf[datadf["length_filter"]]["percentIdentity"],
                names=["Aligned read length", "Percent identity"],
                path=settings["path"] + "PercentIdentityvsAlignedReadLength",
                color=color,
                figformat=settings["format"],
                plots=plotdict,
                stat=stats.pearsonr if not settings["hide_stats"] else None,
                log=settings["logBool"],
                minvaly=minPID,
                title=settings["title"],
                plot_settings=plot_settings)
        )
        plots.append(nanoplotter.dynamic_histogram(array=datadf["percentIdentity"],
                                                   name="percent identity",
                                                   path=settings["path"]
                                                   + "PercentIdentityHistogram",
                                                   title=settings["title"],
                                                   color=color))
        logging.info("Created Percent ID vs Length plot")
    return plots


def make_report(plots, settings):
    '''
    Creates a fat html report based on the previously created files
    plots is a list of Plot objects defined by a path and title
    statsfile is the file to which the stats have been saved,
    which is parsed to a table (rather dodgy)
    '''
    logging.info("Writing html report.")
    html_content = ['<body>']

    # Hyperlink Table of Contents panel
    html_content.append('<div class="panel panelC">')
    if settings["filtered"]:
        html_content.append(
            '<p><strong><a href="#stats0">Summary Statistics prior to filtering</a></strong></p>')
        html_content.append(
            '<p><strong><a href="#stats1">Summary Statistics after filtering</a></strong></p>')
    else:
        html_content.append(
            '<p><strong><a href="#stats0">Summary Statistics</a></strong></p>')
    html_content.append('<p><strong><a href="#plots">Plots</a></strong></p>')
    html_content.extend(['<p style="margin-left:20px"><a href="#'
                         + p.title.replace(' ', '_') + '">' + p.title + '</a></p>' for p in plots])
    html_content.append('</div>')

    # The report itself: stats
    html_content.append('<div class="panel panelM"> <h1>NanoPlot report</h1>')
    if settings["filtered"]:
        html_content.append('<h2 id="stats0">Summary statistics prior to filtering</h2>')
        html_content.append(utils.stats2html(settings["statsfile"][0]))
        html_content.append('<h2 id="stats1">Summary statistics after filtering</h2>')
        html_content.append(utils.stats2html(settings["statsfile"][1]))
    else:
        html_content.append('<h2 id="stats0">Summary statistics</h2>')
        html_content.append(utils.stats2html(settings["statsfile"][0]))

    # The report itself: plots
    html_content.append('<h2 id="plots">Plots</h2>')
    for plot in plots:
        html_content.append('\n<h3 id="' + plot.title.replace(' ', '_') + '">'
                            + plot.title + '</h3>\n' + plot.encode())
        html_content.append('\n<br>\n<br>\n<br>\n<br>')
    html_body = '\n'.join(html_content) + '</div></body></html>'
    html_str = utils.html_head + html_body
    htmlreport = settings["path"] + "NanoPlot-report.html"
    with open(htmlreport, "w") as html_file:
        html_file.write(html_str)
    return htmlreport


if __name__ == "__main__":
    main()

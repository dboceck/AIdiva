import pyBigWig as pw
import pandas as pd
import argparse


def extract_value(row, bw_file):
    if len(row["REF"]) == 1 & len(row["ALT"]) == 1:
        start = row["POS"] - 1
        end = row["POS"]
        chrom = str(row["CHROM"])

        # make sure to use the right chromosome identifier
        if chrom == "MT":
            chrom = "M"

        return bw_file.values("chr" + chrom, start, end)[0]

    elif len(row["REF"]) > 1 | len(row["ALT"]) > 1:
        # for indels take 2 positions before and 2 afterwards also into account
        start = row["POS"] - 3
        end = row["POS"] + len(row["REF"]) + 2

        # make sure to use the right chromosome identifier
        if chrom == "MT":
            chrom == "M"

        return mean(bw_file.values("chr" + chrom, start, end))

    else:
        print("ERROR: Something went wrong the Ref or Alt entry was invalid!")
        print("Ref: ", row["REF"])
        print("Alt: ", row["ALT"])

        exit(1)


def extract_data(data, feature_name, bw_file):
    data[[feature_name]] = data.apply(lambda row: pd.Series(extract_value(row, bw_file)), axis=1)
    return data


def group_and_process_data(bigwig_data, input_data, feature_name):
    bw_file = pw.open(bigwig_data)

    if not bw_file.isBigWig():
        print("The given file is not in BigWig format!!!")

    data_grouped = [group for key, group in input_data.groupby("CHROM")]

    for group in data_grouped:
        group = extract_data(group, feature_name, bw_file)

    data_combined = pd.concat(data_grouped)

    return data_combined


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in_data", type=str, dest="in_data", metavar="in.csv", required=True, help="CSV file containing the data, you want to extend with the ABB score information\n")
    parser.add_argument("--bigwig_data", type=str, dest="bigwig_data", metavar="data.bw", required=True, help="Bigwig file containing the feature information you want to add\n")
    parser.add_argument("--feature_name", type=str, dest="feature_name", metavar="name", required=True, help="Name with whom the feature should appear in the feature table\n")
    parser.add_argument("--out_data", type=str, dest="out_data", metavar="out.csv", required=True, help="Specifies the extended output file\n")
    args = parser.parse_args()

    input_data = pd.read_csv(args.in_data, sep="\t", low_memory=False)
    input_data.sort_index()
    processed_data = group_and_process_data(args.bigwig_data, input_data, args.feature_name)
    processed_data.to_csv(args.out_data, sep="\t", index=False)

from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import make_classification
from sklearn.model_selection import RandomizedSearchCV
from sklearn.model_selection import GridSearchCV
import pandas as pd
import numpy as np
from pprint import pprint
import argparse
import pickle


random_seed = 14038


def import_model(model_file):
    model_to_import = open(model_file, "rb")
    rf_model = pickle.load(model_to_import)
    model_to_import.close()

    return rf_model


def read_input_data(input_file):
    input_data = pd.read_csv(input_file, sep="\t", low_memory=False)

    return input_data


# make sure to use the same features, that were used for the training of the model
def prepare_input_data(input_data, allele_frequency_list, feature_list):
    # fill SegDup missing values with -> 0
    # fill ABB_SCORE missing values with -> 0
    # fill Allele Frequence missing values with -> 0
    # fill missing values from other features with -> median

    for allele_frequency in allele_frequency_list:
        input_data[allele_frequency] = input_data[allele_frequency].fillna(0)
        input_data[allele_frequency] = input_data[allele_frequency].apply(lambda row: pd.Series(max([float(frequency) for frequency in str(row).split("&")], default=np.nan)))

    # compute maximum Minor Allele Frequency (MAF)
    input_data["MaxAF"] = input_data.apply(lambda row: pd.Series(max([float(frequency) for frequency in row[allele_frequency_list].tolist()])), axis=1)

    for feature in feature_list:
        if feature == "MaxAF":
            input_data[feature] = input_data[feature].fillna(0)
        elif feature == "segmentDuplication":
            input_data[feature] = input_data[feature].apply(lambda row: max([float(value) for value in str(row).split("&") if ((value != ".") & (value != "nan") & (value != ""))], default=np.nan))
            input_data[feature] = input_data[feature].fillna(0)
        elif feature == "ABB_SCORE":
            input_data[feature] = input_data[feature].fillna(0)
        elif "SIFT" in feature:
            (input_data[feature])
            input_data[feature] = input_data[feature].apply(lambda row: min([float(value) for value in str(row).split("&") if ((value != ".") & (value != "nan") & (value != ""))], default=np.nan))
            input_data[feature] = input_data[feature].fillna(input_data[feature].median())
        else:
            input_data[feature] = input_data[feature].apply(lambda row: max([float(value) for value in str(row).split("&") if ((value != ".") & (value != "nan") & (value != ""))], default=np.nan))
            input_data[feature] = input_data[feature].fillna(input_data[feature].median())

    input_features = np.asarray(input_data[feature_list])

    # TODO add workaround to handle the rare case that for one of the features only NaNs are present and therefor the median leads also to a nan
    # in that case the input features contains NaNs and lead to an error

    return input_data, input_features


def predict_pathogenicity(rf_model_snps, rf_model_indel, input_data_snps, input_features_snps, input_data_indel, input_features_indel):
    class_prediction_snps = rf_model_snps.predict(input_features_snps)
    score_prediction_snps = pd.DataFrame(rf_model_snps.predict_proba(input_features_snps), columns=["Probability_Benign", "Probability_Pathogenic"])

    class_prediction_indel = rf_model_indel.predict(input_features_indel)
    score_prediction_indel = pd.DataFrame(rf_model_indel.predict_proba(input_features_indel), columns=["Probability_Benign", "Probability_Pathogenic"])

    input_data_snps["AIDIVA_SCORE"] = score_prediction_snps["Probability_Pathogenic"]
    input_data_indel["AIDIVA_SCORE"] = score_prediction_indel["Probability_Pathogenic"]

    return input_data_snps, input_data_indel


def check_coding(coding_regions, variant_to_check):
    if coding_regions[(coding_regions.CHROM == variant_to_check["CHROM"]) & (coding_regions.START.le(variant_to_check["POS"])) & (coding_regions.START.ge(variant_to_check["POS"]))].empty:
        return 0
    else:
        return 1


def perform_pathogenicity_score_prediction(input_data_snps, input_data_indel, rf_model_snps, rf_model_indel, allele_frequency_list, feature_list, coding_regions):
    prepared_input_data_snps, input_features_snps = prepare_input_data(input_data_snps, allele_frequency_list, feature_list)
    prepared_input_data_indel, input_features_indel = prepare_input_data(input_data_indel, allele_frequency_list, feature_list)

    rf_model_snps = import_model(rf_model_snps)
    rf_model_indel = import_model(rf_model_indel)

    ## TODO: Filter variants, only coding variants should be scored
    input_data_snps["CODING"] = input_data_snps.apply(lambda row: check_coding(coding_regions, row), axis=1)
    input_data_indel["CODING"] = input_data_indel.apply(lambda row: check_coding(coding_regions, row), axis=1)

    predicted_data_snps, predicted_data_indel = predict_pathogenicity(rf_model_snps, rf_model_indel, prepared_input_data_snps, input_features_snps, prepared_input_data_indel, input_features_indel)

    # set the score for frameshift variants always to 1.0
    # the following line might produce an SettingWithCopyWarning this Warning should be a false positive in this case
    predicted_data_indel.loc[(abs(predicted_data_indel.REF.str.len() - predicted_data_indel.ALT.str.len()) % 3 != 0), "AIDIVA_SCORE"] = 1.0

    # set score for non-coding variants to -1 or NaN
    # the models are only for coding variants
    predicted_data_snps.loc[(predicted_data_snps.CODING == 0), "AIDIVA_SCORE"] = -1
    predicted_data_indel.loc[(predicted_data_indel.CODING == 0), "AIDIVA_SCORE"] = -1

    # TODO set splicing donor/acceptor variants to 1.0
    predicted_data_snps.loc[(predicted_data_snps.Consequence.str.contains("splice_acceptor_variant") | predicted_data_snps.Consequence.str.contains("splice_donor_variant")), "AIDIVA_SCORE"] = 1.0
    predicted_data_indel.loc[(predicted_data_indel.Consequence.str.contains("splice_acceptor_variant") | predicted_data_indel.Consequence.str.contains("splice_donor_variant")), "AIDIVA_SCORE"] = 1.0

    ## TODO: set synonymous variants to 0.0
    predicted_data_snps.loc[(predicted_data_snps.Consequence.str.contains("synonymous")), "AIDIVA_SCORE"] = 0.0
    predicted_data_indel.loc[(predicted_data_indel.Consequence.str.contains("synonymous")), "AIDIVA_SCORE"] = 0.0


    return predicted_data_snps, predicted_data_indel


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in_data_snps", type=str, dest="in_data_snps", metavar="in.csv", required=True, help="CSV file containing the training data, used to train the random forest model\n")
    parser.add_argument("--in_data_indel", type=str, dest="in_data_indel", metavar="in.csv", required=True, help="CSV file containing the training data, used to train the random forest model\n")
    parser.add_argument("--out_data", type=str, dest="out_data", metavar="out.csv", required=True, help="CSV file containing the test data, used to compute the model statistics\n")
    parser.add_argument("--model_snps", type=str, dest="model_snps", metavar="model_snps.pkl", required=True, help="Specifies the name of the trained snps model to import\n")
    parser.add_argument("--model_indel", type=str, dest="model_indel", metavar="model_indel.pkl", required=True, help="Specifies the name of the trained indel model to import\n")
    parser.add_argument("--allele_frequency_list", type=str, dest="allele_frequency_list", metavar="frequency1,frequecy2,frequency3", required=False, help="Comma separated list of the allele frequency sources that should be used as basis to get the maximum allele frequency\n")
    parser.add_argument("--feature_list", type=str, dest="feature_list", metavar="feature1,feature2,feature3", required=True, help="Comma separated list of the features used to train the model\n")
    args = parser.parse_args()
    parser.add_argument("--coding_regions", type=str, dest="coding_regions", metavar="coding_regions.bed", required=True, help="Bed file containing the coding regions of the reference assembly\n")
    args = parser.parse_args()

    rf_model_snps = import_model(args.model_snps)
    rf_model_indel = import_model(args.model_indel)

    input_data_snps = read_input_data(args.in_data_snps)
    input_data_indel = read_input_data(args.in_data_indel)

    allele_frequency_list = args.allele_frequency_list.split(",")
    feature_list = args.feature_list.split(",")

    coding_regions = pd.read_csv(args.coding_regions, sep="\t", names=["CHROM", "START", "END"], low_memory=False)

    # if multiple alleles are reported consider only the first one
    # TODO decide how to handle allele ambiguity
    #input_data["ALT"] = input_data["ALT"].map(lambda x: x.split(",")[0])

    #input_data_snps = input_data[(input_data["REF"].apply(len) == 1) & (input_data["ALT"].apply(len) == 1)]
    #input_data_indel = input_data[(input_data["REF"].apply(len) > 1) | (input_data["ALT"].apply(len) > 1)]

    #TODO add indel handling call functions from other script to expand and then call vep and afterwards combine

    prepared_input_data_snps, input_features_snps = prepare_input_data(input_data_snps, allele_frequency_list, feature_list)
    prepared_input_data_indel, input_features_indel = prepare_input_data(input_data_indel, allele_frequency_list, feature_list)

    predicted_data_snps, predicted_data_indel = predict_rank(rf_model_snps, rf_model_indel, prepared_input_data_snps, input_features_snps, prepared_input_data_indel, input_features_indel)

    predicted_data_combined = pd.concat([predicted_data_snps, predicted_data_indel], sort=False)
    predicted_data_combined.sort_values(["CHROM", "POS"], ascending=[True, True])

    predicted_data_combined.to_csv(args.out_data, index=False, sep="\t", na_rep="NA")

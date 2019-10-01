import os
import sys
import importlib
import argparse
import warnings
import flywheel
import pprint
import logging
import re
import pandas as pd
from pathlib import Path
from ..convert import get_nested

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('fw-heudiconv-curator')


def get_BIDS_label_from_session(ses_object, regex='sub'):

    logger.debug("Processing session {}...".format(ses_object.label))
    acquisitions = ses_object.acquisitions()
    pattern = re.compile(r"(?<={}-)[a-zA-z0-9]+(?=_)".format(regex))

    bids_labels = []
    for x in acquisitions:
        files = [f for f in x.files if "nifti" in f.type]
        for y in files:
            bids_labels.append(get_nested(y.to_dict(), 'info', 'BIDS', 'Filename'))
    if bids_labels:
        for b in range(len(bids_labels)):
            if bids_labels[b] is not None:
                label = pattern.search(bids_labels[b])
                if label:
                    bids_labels[b] = label.group()
                else:
                    bids_labels[b] = None

    final_label = set(filter(None, bids_labels))
    if len(final_label) == 1:
        return final_label.pop()
    else:
        return None



def initialise_dataset(client, project_label, subject_labels=None, session_labels=None, dry_run=True):

    if dry_run:
        logger.setLevel(logging.DEBUG)
    logger.info("Querying Flywheel server...")
    project_obj = client.projects.find_first('label="{}"'.format(project_label))
    assert project_obj, "Project not found! Maybe check spelling...?"
    logger.debug('Found project: %s (%s)', project_obj['label'], project_obj.id)
    sessions = client.get_project_sessions(project_obj.id)
    # filters
    if subject_labels:
        sessions = [s for s in sessions if s.subject['label'] in subject_labels]
    if session_labels:
        sessions = [s for s in sessions if s.label in session_labels]

    return sessions


def attach_to_object(object, file):

    my_file = Path(file)
    if my_file.is_file():
        object.upload_file(my_file)
        return 0
    else:
        logger.error("Couldn't access file {}".format(file))
        return 1


def autogen_participants_meta(sessions):

    logger.error("Not yet implemented")
    return 0


def autogen_sessions_meta(sessions):

    logger.error("Not yet implemented")
    return 0


def preproc_sessions_tsvs(sessions, input_file):

    logger.error("Not yet implemented")
    # df = pd.read_csv(input_file)
    #
    # for x in sessions
    # subset and create a dictionary of session object: session.tsv file
    # return dict
    return 0


def get_parser():

    parser = argparse.ArgumentParser(
        description="Curate BIDS metadata on Flywheel\n\nSee the BIDS spec for details: https://bids-specification.readthedocs.io/en/stable/03-modality-agnostic-files.html",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "--project",
        help="The project in flywheel",
        required=True
    )
    parser.add_argument(
        "--subject",
        help="The subject label(s)",
        nargs="+",
        default=None
    )
    parser.add_argument(
        "--session",
        help="The session label(s)",
        nargs="+",
        default=None
    )
    parser.add_argument(
        "--verbose",
        help="Print ongoing messages of progress",
        action='store_true',
        default=False
    )
    parser.add_argument(
        "--dry-run",
        help="Don't apply changes",
        action='store_true',
        default=False
    )

    # participants metadata
    participants_meta = parser.add_mutually_exclusive_group()
    participants_meta.add_argument(
        "--autogen-participants-meta",
        help="Automatically generate participants.tsv metadata",
        action='store_true',
        default=False
    )
    participants_meta.add_argument(
        "--upload-participants-meta",
        help="Path to a participants.tsv metadata file to upload",
        action='store'
    )

    # sessions metadata
    sessions_meta = parser.add_mutually_exclusive_group()
    sessions_meta.add_argument(
        "--autogen-sessions-meta",
        help="Automatically generate sub-<label>_sessions.tsv metadata",
        action='store_true',
        default=False
    )
    sessions_meta.add_argument(
        "--upload-sessions-meta",
        help="Path to a sessions.tsv metadata file to upload",
        action='store'
    )

    # scans file
    parser.add_argument(
        "--scans",
        help="Path to a scans.tsv metadata file to upload",
        action='store'
    )

    # dataset descr file
    parser.add_argument(
        "--dataset-description",
        help="Path to a dataset_description.json metadata file to upload",
        action='store'
    )

    # code files
    parser.add_argument(
        "--code",
        help="Path(s) to additional code files to upload",
        nargs='+',
        action='store'
    )

    # readme file
    parser.add_argument(
        "--readme",
        help="Path to README file to upload",
        action='store'
    )

    # changes file
    parser.add_argument(
        "--changes",
        help="Path to CHANGES file to upload",
        action='store'
    )

    return parser


def main():
    status = [0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fw = flywheel.Client()
    assert fw, "Your Flywheel CLI credentials aren't set!"
    parser = get_parser()
    args = parser.parse_args()

    # Print a lot if requested
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    print(args)

    sessions = initialise_dataset(fw, args.project, args.subject, args.session, args.dry_run)

    if len(sessions) < 1:
        status = 1
        logger.error("No sessions found!")
        sys.exit(status)

    project_level_uploads = {
        'README': args.readme,
        'CHANGES': args.changes,
        'CODE': args.code,
        'dataset_description.json': args.dataset_description
    }

    for k,v in project_level_uploads.items():

        if v is not None:
            logger.info("Attempting to attach {} to project".format(v))
            status.append(attach_to_object(fw.get(sessions[0].project), v))

    if args.autogen_participants_meta:

        logger.info("Auto-generating participants.tsv...")
        status.append(autogen_participants_meta(sessions))

    elif args.upload_participants_meta:

        logger.info("Attempting to attach {} to project...".format(args.upload_participants_meta))
        status.append(attach_to_object(fw.get(sessions[0].project), args.upload_participants_meta))

    if args.autogen_sessions_meta:

        logger.info("Auto-generating *_sessions.tsv...")
        status.append(autogen_sessions_meta(sessions))

    elif args.upload_sessions_meta:

        logger.info("Attempting to attach {} to each subject...".format(args.upload_participants_meta))
        sess_meta_dict = preproc_sessions_tsvs(sessions, args.upload_participants_meta)

        for k, v in sess_meta_dict.items():
            #write pandas value v to file
            status.append(attach_to_object(k, v))
            #delete file v

    if any([x == 1 for x in status]):
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()

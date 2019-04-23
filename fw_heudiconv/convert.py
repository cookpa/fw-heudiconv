import os
import ast
"""
info = {
    (
        '{bids_subject_session_dir}/dwi/{bids_subject_session_prefix}_acq-multishell_dir-AP_dwi_dwi__dup-02',
        ('nii.gz', 'dicom'),
        None
    ): [None]
}
id = {'locator': 'unknown', 'session': 'None', 'subject': '20448'}
"""
# def convert(info):
#     """Using an id and an info object, will format it into a flywheel BIDS
#     standard object
#
#     Args:
#         _id (dict): The dictionary returned from the infotoid
#         info (dict): The info returned from the infotodict function
#     Returns:
#         dict: A BIDS namespace update to send via sdk
#     """
#     for info_key in info.keys():
#         bids_subject_session_dir = 'sub-{}/sub-{}'.format(_id['subject'], _id['session'] if _id['session'] not in ['None', None] else 'sub-{}'.format(_id['subject']),
#         bids_subject_session_prefix = bids_subject_session_dir.replace('/', '_')
#
#         full_path = info_key[0].format({
#             'bids_subject_session_dir': bids_subject_session_dir,
#             'bids_subject_session_prefix': bids_subject_session_prefix
#         })
#
#         BIDS = {
#             'Filename': os.path.basename(full_path),
#             'Path': os.path.dirname(full_path),
#             'Folder': info_key.split('/')[1],
#             'valid': True,
#             'ignore': 'dup' in os.path.basename(full_path)
#         }

def apply_conversion(client, to_rename, subj_label=None, sess_label=None, verbose=True):
    """Applies the BIDS naming convention found in the heuristic to the current
    collection of files. Updates all BIDS fields and defines intentions for
    fieldmap files.

    Args:
        client (Client): The flywheel sdk client
        to_rename (dict): A dictionary of the session's files to be renamed
        subj_label (str): The subject label
        sess_label (str): The session label
        verbose (bool): Print progress messages
    """


    intended = []
    suffixes = {'nifti': ".nii.gz", 'bval': ".bval", 'bvec': ".bvec"}
    ftypes = ['nifti', 'bval', 'bvec']
    FAILS = []
    all_acquisitions = [client.get(val[0]) for _, val in to_rename.items() if val]

    # get subj and sess labels if not set
    if subj_label is None:
        subj_label = client.get(all_acquisitions[0].parents['subject']).label
    if sess_label is None:
        sess_label = client.get(all_acquisitions[0].parents['session']).label

    if verbose:
        print("\nUpdating BIDS info for subject {} session {}:".format(subj_label, sess_label))
        print("=========================================================")
    for key, val in to_rename.items():
        if not val:
            continue

        # make a bids dictionary
        bids_keys = ['sub', 'ses', 'folder', 'name']
        bids_vals = key[0].format(subject=subj_label, session="ses-"+sess_label).split("/")
        bids_dict = dict(zip(bids_keys, bids_vals))

        # get the acquisition object
        acq_id = val[0]
        try:
            acq = client.get(acq_id)
            files = [f for f in acq.files if f.type in ftypes]
        except Exception as e:
            print("Could not query flywheel to apply BIDS changes!")
            print(e)
            error = {'subject': subj_label,
                     'session': sess_label,
                     'job': 'query files',
                     'reason': e}
            FAILS.append(error)
            continue

        for f in files:

            if verbose:
                print("\n--------")
                print(f.name, "\n")

            # special check for magnitude files
            if "e1.nii.gz" in f.name:
                suffix = "1" + suffixes[f.type]
            elif "e2.nii.gz" in f.name:
                suffix = "2" + suffixes[f.type]
            else:
                suffix = suffixes[f.type]

            try:
                if verbose: print("Old BIDS:")
                if 'BIDS' in f.info:
                    if verbose: print(f.info['BIDS'])
                    new_bids = f.info['BIDS']
                else:
                    if verbose: print('None [WARNING: populating an empty dictionary as'\
                    " bids-curation hasn't been run]")
                    new_bids = add_empty_bids_fields(bids_dict['folder'], bids_dict['name'])

                new_bids['Filename'] = bids_dict['name']+suffix
                new_bids['Folder'] = bids_dict['folder']
                new_bids['Path'] = "/".join([bids_dict['sub'],
                                            bids_dict['ses'],
                                            bids_dict['folder']])
                new_bids['error_message'] = ""
                new_bids['valid'] = True
            except Exception as e:
                print("Couldn't set BIDS data for file ", f.name)
                print("Maybe BIDS curation hasn't been run...?")

                error = {'subject': subj_label,
                         'session': sess_label,
                         'job': 'query files',
                         'reason': e}
                FAILS.append(error)
                continue

            if verbose:
                print("\nNew BIDS:")
                print(new_bids)
                print("--------")

            try:
                acq.update_file_info(f.name, {'BIDS': new_bids})
            except Exception as e:
                print("Unable to update file ", f.name)
                print(e)
                error = {'subject': subj_label,
                         'session': sess_label,
                         'job': 'update file',
                         'reason': e}
                FAILS.append(error)
                continue

            # track intention updates
            if "IntendedFor" in new_bids and bool(new_bids['IntendedFor']):
                intended.append((key, val))

    # update file intentions for each intended
    if verbose:
        print("\nUpdating fieldmap intentions: {} {}".format(subj_label, sess_label))
        print("=========================================================")

    # get all of the files in this session
    all_files = []

    for acq in all_acquisitions:
        for f in acq.files:
            if f.type in ['nifti', 'bval', 'bvec']:
                all_files.append(f)

    # loop over the intented files
    if intended:
        for key, val in intended:

            acq_id = val[0]
            try:
                acq = client.get(acq_id)
                acquisition_files = [f for f in acq.files if f.type in ftypes]
            except Exception as e:
                print("Could not query flywheel to apply intentions!")
                print(e)
                error = {'subject': subj_label, 'session': sess_label, 'job': 'query files', 'reason': e}
                FAILS.append(error)
                continue

            if verbose: print("\nFor acquisition: ", acq.label)

            # (have to update each file in the acquisition)
            for f in acquisition_files:
                intent = [x["Folder"] for x in ast.literal_eval(f.info['BIDS']['IntendedFor'])]
                if verbose: print(f.name, "intended For: ", intent)

                # loop through all files and add any with matching intent to target files
                target_files = []

                for g in all_files:
                    if "BIDS" in g.info.keys() and g.info['BIDS'] != "NA":
                        if g.info['BIDS']['Folder'] in intent and ".nii.gz" in g.info['BIDS']['Filename']:

                            # build appropriate bids name for intention path
                            path = key[0].format(subject=subj_label, session="ses-"+sess_label).split("/")[1]
                            path = "/".join([path, g.info['BIDS']['Folder'], g.info['BIDS']['Filename']])
                            target_files.append(path)

                if verbose: print("Files: ", target_files)

                try:
                    acq.update_file_info(f.name, {'IntendedFor': target_files})
                except Exception as e:
                    print("Unable to update intentions", f.name)
                    print(e)
                    error = {'subject': subj_label, 'session': sess_label, 'job': 'update intentions', 'reason': e}
                    FAILS.append(error)
                    continue


    if verbose: print("\nUpdates complete\n")
    return(FAILS)

# To do:
def add_empty_bids_fields(folder, fname=None):

    if "fmap" in folder:
        if not fname:
            print("No filename given, can't set intentions for this fieldmap!")
        elif "epi" in fname:
            IntendedFor = "[{'Folder': 'dwi'}]"
            Modality = "epi"
        else:
            IntendedFor = "[{'Folder': 'func'}]"
            Modality = "fieldmap"
        new_bids = {"Acq": "",
                    "Ce": "",
                    "Dir": "",
                    "Echo": "",
                    "error_message": "",
                    "Filename": "",
                    "Folder": "fmap",
                    "ignore": "",
                    "IntendedFor": IntendedFor,
                    "Mod": "",
                    "Modality": Modality,
                    "Path": "",
                    "Rec": "",
                    "Run": "",
                    "Task": "",
                    "template": "fieldmap_file",
                    "valid": False}

    elif "dwi" in folder:

        new_bids = {"Acq": "",
                    "Ce": "",
                    "Dir": "",
                    "Echo": "",
                    "error_message": "",
                    "Filename": "",
                    "Folder": "",
                    "ignore": "",
                    "IntendedFor": "",
                    "Mod": "",
                    "Modality": "dwi",
                    "Path": "",
                    "Rec": "",
                    "Run": "",
                    "Task": "",
                    "template": "diffusion_file",
                    "valid": False}

    elif "func" in folder:

        new_bids = {"Acq": "",
                    "Ce": "",
                    "Dir": "",
                    "Echo": "",
                    "error_message": "",
                    "Filename": "",
                    "Folder": "",
                    "ignore": "",
                    "IntendedFor": "",
                    "Mod": "",
                    "Modality": "",
                    "Path": "",
                    "Rec": "",
                    "Run": "",
                    "Task": "",
                    "template": "",
                    "valid": False}

    elif "anat" in folder:

        new_bids = {"Acq": "",
                    "Ce": "",
                    "Dir": "",
                    "Echo": "",
                    "error_message": "",
                    "Filename": "",
                    "Folder": "anat",
                    "ignore": "",
                    "IntendedFor": "",
                    "Mod": "",
                    "Modality": "T1w",
                    "Path": "",
                    "Rec": "",
                    "Run": "",
                    "Task": "",
                    "template": "anat_file",
                    "valid": False}

    else:

        new_bids = {"Acq": "",
                    "Ce": "",
                    "Dir": "",
                    "Echo": "",
                    "error_message": "",
                    "Filename": "",
                    "Folder": "",
                    "ignore": "",
                    "IntendedFor": "",
                    "Mod": "",
                    "Modality": "",
                    "Path": "",
                    "Rec": "",
                    "Run": "",
                    "Task": "",
                    "template": "",
                    "valid": False}

    return(new_bids)

#!/usr/bin/env python
"""
Functions for processing nested sampling runs.
"""

import numpy as np
import nestcheck.io_utils as iou


def get_polychord_data(file_root, n_runs, **kwargs):
    """
    Load and process polychord chains
    """
    cache_dir = kwargs.pop('cache_dir', 'cache')
    base_dir = kwargs.pop('base_dir', 'chains')
    load = kwargs.pop('load', False)
    save = kwargs.pop('save', False)
    logl_warn_only = kwargs.pop('logl_warn_only', True)
    overwrite_existing = kwargs.pop('overwrite_existing', False)
    if kwargs:
        raise TypeError('Unexpected **kwargs: {0}'.format(kwargs))
    save_name = file_root + '_' + str(n_runs) + 'runs'
    if load:
        try:
            return iou.pickle_load(cache_dir + '/' + save_name)
        except OSError:  # FileNotFoundError is a subclass of OSError
            pass
    data = []
    errors = {}
    # load and process chains
    for i in range(1, n_runs + 1):
        try:
            data.append(process_polychord_run(
                file_root + '_' + str(i), base_dir,
                logl_warn_only=logl_warn_only))
        except (OSError, AssertionError, KeyError) as err:
            try:
                errors[type(err).__name__].append(i)
            except KeyError:
                errors[type(err).__name__] = [i]
    for error_name, val_list in errors.items():
        if val_list:
            save = False  # only save if every file is processed ok
            message = (error_name + ' processing ' + str(len(val_list)) + ' / '
                       + str(n_runs) + ' files')
            if len(val_list) != n_runs:
                message += ('. Runs with errors have roots ending with: ' +
                            str(val_list))
            print(message)
    if save:
        print('Processed new chains: saving to ' + save_name)
        iou.pickle_save(data, cache_dir + '/' + save_name, print_time=False,
                        overwrite_existing=overwrite_existing)
    return data


def check_ns_run(run, logl_warn_only=False):
    """Checks a nested sampling run has some of the expected properties."""
    assert isinstance(run, dict)
    check_ns_run_members(run)
    check_ns_run_logls(run, warn_only=logl_warn_only)
    check_ns_run_threads(run)


def check_ns_run_members(run):
    """Checks a nested sampling run has some of the expected properties."""
    run_keys = list(run.keys())
    # Mandatory keys
    for key in ['logl', 'nlive_array', 'theta', 'thread_labels',
                'thread_min_max']:
        assert key in run_keys
        run_keys.remove(key)
    # Optional keys
    # for key in ['settings', 'output']:
    for key in ['output']:
        try:
            run_keys.remove(key)
        except ValueError:
            pass
    # Check for unexpected keys
    assert not run_keys, 'Unexpected keys in ns_run: ' + str(run_keys)
    # Check type of mandatory members
    for key in ['logl', 'nlive_array', 'theta', 'thread_labels',
                'thread_min_max']:
        assert isinstance(run[key], np.ndarray), key + ' is type ' + type(key)
    # check shapes of keys
    assert run['logl'].ndim == 1
    assert run['logl'].shape == run['nlive_array'].shape
    assert run['logl'].shape == run['thread_labels'].shape
    assert run['theta'].ndim == 2
    assert run['logl'].shape[0] == run['theta'].shape[0]


def check_ns_run_logls(run, warn_only=False):
    # Test logls are unique and in the correct order
    assert np.array_equal(run['logl'], run['logl'][np.argsort(run['logl'])])
    logl_u, counts = np.unique(run['logl'], return_counts=True)
    repeat_logls = run['logl'].shape[0] - logl_u.shape[0]
    if repeat_logls != 0:
        msg = ('# unique logl values is ' + str(repeat_logls) +
               ' less than # points. Duplicate values: ' +
               str(logl_u[np.where(counts > 1)[0]]))
        if logl_u.shape[0] != 1:
            msg += (', Counts: ' + str(counts[np.where(counts > 1)[0]]) +
                    ', First point at inds ' +
                    str(np.where(run['logl'] ==
                        logl_u[np.where(counts > 1)[0][0]])[0]) +
                    ' out of ' + str(run['logl'].shape[0]))
    if not warn_only:
        assert repeat_logls == 0, msg
    else:
        if repeat_logls != 0:
            print('WARNING: ' + msg)


def check_ns_run_threads(run):
    # Check thread labels
    assert run['thread_labels'].dtype == int
    uniq_th = np.unique(run['thread_labels'])
    assert np.array_equal(
        np.asarray(range(run['thread_min_max'].shape[0])), uniq_th), \
        str(uniq_th)
    # Check thread_min_max
    assert np.any(run['thread_min_max'][:, 0] == -np.inf), \
        ('Run should have at least one thread which starts by sampling the ' +
         'whole prior')
    for th_lab in uniq_th:
        inds = np.where(run['thread_labels'] == th_lab)[0]
        assert run['thread_min_max'][th_lab, 0] < run['logl'][inds[0]], \
            ('First point in thread has logl less than thread min logl! ' +
             str(th_lab) + ', ' + str(run['logl'][inds[0]]),
             str(run['thread_min_max'][th_lab, :]))
        assert run['thread_min_max'][th_lab, 1] == run['logl'][inds[-1]], \
            ('Last point in thread logl != thread end logl! ' +
             str(th_lab) + ', ' + str(run['logl'][inds[0]]),
             str(run['thread_min_max'][th_lab, :]))


def process_polychord_run(file_root, base_dir, logl_warn_only=False):
    """
    Loads data from PolyChord run into the standard nestcheck format.
    """
    dead_points = np.loadtxt(base_dir + '/' + file_root + '_dead-birth.txt')
    ns_run = process_polychord_dead_points(dead_points)
    try:
        from PyPolyChord.output import PolyChordOutput
        ns_run['output'] = PolyChordOutput(base_dir, file_root).__dict__
    except ImportError:
        print('Failed to import PyPolyChord.output.PolyChordOutput')
    # try:
    #     info = iou.pickle_load(root + '_info')
    #     for key in ['output', 'settings']:
    #         assert key not in ns_run
    #         ns_run[key] = info.pop(key)
    #     assert not info
    #     # Run some tests based on the settings
    #     # ------------------------------------
    #     # For the standard ns case
    #     if not ns_run['settings']['nlives']:
    #         nthread = ns_run['thread_min_max'].shape[0]
    #         assert nthread == ns_run['settings']['nlive'], \
    #             str(nthread) + '!=' + str(ns_run['settings']['nlive'])
    #         standard_nlive_array = np.zeros(ns_run['logl'].shape)
    #         standard_nlive_array += ns_run['settings']['nlive']
    #         for i in range(1, ns_run['settings']['nlive']):
    #             standard_nlive_array[-i] = i
    #         assert np.array_equal(ns_run['nlive_array'],
    #                               standard_nlive_array)
    # except OSError:
    #     pass
    check_ns_run(ns_run, logl_warn_only=logl_warn_only)
    return ns_run


def process_polychord_dead_points(dead_points, init_birth=-1e+30):
    """
    Process a nested sampling dead points file.
    """
    dead_points = dead_points[np.argsort(dead_points[:, -2])]
    ns_run = {}
    ns_run['logl'] = dead_points[:, -2]
    repeat_logls = (ns_run['logl'].shape[0] -
                    np.unique(ns_run['logl']).shape[0])
    assert repeat_logls == 0, \
        '# unique logl values is ' + str(repeat_logls) + ' less than #point'
    ns_run['theta'] = dead_points[:, :-2]
    birth_contours = dead_points[:, -1]
    ns_run['thread_labels'] = threads_given_birth_contours(
        ns_run['logl'], birth_contours, init_birth=init_birth)
    unique_threads = np.unique(ns_run['thread_labels'])
    assert np.array_equal(unique_threads,
                          np.asarray(range(unique_threads.shape[0])))
    # Work out nlive_array and thread_min_max logls from thread labels and
    # birth contours
    thread_min_max = np.zeros((unique_threads.shape[0], 2))
    # NB delta_nlive indexes are offset from points' indexes by 1 as we need an
    # element to repesent the initial sampling of live points before any dead
    # points are created.
    # I.E. birth on step 1 corresponds to replacing dead point zero
    delta_nlive = np.zeros(dead_points.shape[0] + 1)
    for label in unique_threads:
        inds = np.where(ns_run['thread_labels'] == label)[0]
        # Max is final logl in thread
        thread_min_max[label, 1] = ns_run['logl'][inds[-1]]
        birth_logl = birth_contours[inds[0]]
        # delta nlive indexes are +1 from logl indexes to allow for initial
        # nlive (before first dead point)
        delta_nlive[inds[-1] + 1] -= 1
        if birth_logl == init_birth:
            # thread minimum is -inf as it starts by sampling from whole prior
            thread_min_max[label, 0] = -np.inf
            delta_nlive[0] += 1
        else:
            thread_min_max[label, 0] = birth_logl
            birth_ind = np.where(ns_run['logl'] == birth_logl)[0]
            assert birth_ind.shape == (1,)
            delta_nlive[birth_ind[0] + 1] += 1
    ns_run['thread_min_max'] = thread_min_max
    ns_run['nlive_array'] = np.cumsum(delta_nlive)[:-1]
    return ns_run


def threads_given_birth_contours(logl, birth_logl, init_birth=-1e+30):
    """
    Divides a nested sampling run into threads, using info on the contours at
    which points were sampled.

    Parameters
    ----------
    logl: 1d numpy array
        logl values of each point.
    birth_logl: 1d numpy array
        logl values of the iso-likelihood contour from within each point was
        sampled (on which it was born).
    init_birth: float or int, optional
        the value used in birth_logl to represent the inital live points
        sampled from the whole prior. PolyChord uses -1e+30

    Returns
    -------
    thread_labels: 1d numpy array of ints
        labels of the thread each point belongs to.
    """
    for i, birth in enumerate(birth_logl):
        assert birth < logl[i], str(birth) + ' ' + str(logl[i])
        assert birth == init_birth or np.where(logl == birth)[0].shape == (1,)
    assert birth_logl[0] == init_birth, str(birth_logl)
    unique, counts = np.unique(birth_logl[np.where(birth_logl != init_birth)],
                               return_counts=True)
    thread_start_logls = np.concatenate((np.asarray([init_birth]),
                                         unique[np.where(counts > 1)]))
    thread_start_counts = np.concatenate(
        (np.asarray([(birth_logl == init_birth).sum()]),
         counts[np.where(counts > 1)] - 1))
    thread_labels = np.full(logl.shape, np.nan)
    thread_num = 0
    for nmulti, multi in enumerate(thread_start_logls):
        for i, start_ind in enumerate(np.where(birth_logl == multi)[0]):
            # unless nmulti=0 the first point born on the contour (i=0) is
            # already assigned to a thread
            if i != 0 or nmulti == 0:
                # check point has not already been assigned
                assert np.isnan(thread_labels[start_ind])
                thread_labels[start_ind] = thread_num
                # find the point which replaced it
                next_ind = np.where(birth_logl == logl[start_ind])[0]
                while next_ind.shape != (0,):
                    # check point has not already been assigned
                    assert np.isnan(thread_labels[next_ind[0]])
                    thread_labels[next_ind[0]] = thread_num
                    # find the point which replaced it
                    next_ind = np.where(birth_logl == logl[next_ind[0]])[0]
                thread_num += 1
    assert np.all(~np.isnan(thread_labels)), \
        ('Some points were not given a thread label! Indexes=' +
         str(np.where(np.isnan(thread_labels))[0]) +
         '\nlogls on which threads start are:' +
         str(thread_start_logls) + ' with num of threads starting on each: ' +
         str(thread_start_counts) +
         '\nthread_labels =' + str(thread_labels))
    assert np.array_equal(thread_labels, thread_labels.astype(int)), \
        'Thread labels should all be ints!'
    thread_labels = thread_labels.astype(int)
    # Check unique thread labels are a sequence from 0 to nthreads-1
    nthreads = sum(thread_start_counts)
    assert np.array_equal(np.unique(thread_labels),
                          np.asarray(range(nthreads))), \
        str(np.unique(thread_labels))
    return thread_labels

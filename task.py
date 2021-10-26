# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tasks triggered by suite scheduler."""
# pylint: disable=dangerous-default-value

from distutils import version
from collections import defaultdict
import logging
import uuid

import analytics
import build_lib
import task_executor
import tot_manager

from multi_duts_lib import BuildTarget, convert_secondary_targets_to_string

# The max lifetime of a suite scheduled by suite scheduler
_JOB_MAX_RUNTIME_MINS_DEFAULT = 40 * 60


class SchedulingError(Exception):
  """Raised to indicate a failure in scheduling a task."""


class Task(object):
  """Represents an entry from the suite_scheduler config file.

  Each entry from the suite_scheduler config file maps one-to-one to a
  Task. Each instance has enough information to schedule itself.
  """

  def __init__(self,
               task_info,
               board_family_config={},
               tot=None,
               is_sanity=False):
    """Initialize a task instance.

    Args:
      task_info: a config_reader.TaskInfo object, which includes:
          name, name of this task, e.g. 'NightlyPower'
          suite, the name of the suite to run, e.g. 'graphics_per-day'
          branch_specs, a pre-vetted iterable of branch specifiers,
            e.g. ['>=R18', 'factory']
          pool, the pool of machines to schedule tasks. Default is None.
          num, the number of devices to shard the test suite. It could
            be an Integer or None. By default it's None.
          analytics_name, the build rule name. Initially build rule or test rule
            name was used in suite scheduler's dashboard for analytics. Later it
            was expanded to the entire pipeline and we want to tag all requests
            from Suite Scheduler with the rule name.
          board_families, a common separated list of board family to run this
            task on. Boards belong to one of the board family in this list
            would be added to task_info.boards.
          boards, a comma separated list of boards to run this task on. Default
            is None, which allows this task to run on all boards. If same board
            is specified in 'boards' and 'exclude_boards', we exclude this
            board.
          dimensions, a comma separated lists of labels. Each label is in
            the form of 'key:value'.
          exclude_board_families, a common separated list of board family not to
            run task on. Boards belong to one of the board family in this list
            would be added to task_info.exclude_boards.
          exclude_boards, a comma separated list of boards not to run this task
            on. Default is None, which allows this task to run on all boards.
            If same board is specified in 'boards' and 'exclude_boards', we
            exclude this board.
          models, a comma separated list of models to run this task on. Default
            is None, which allows this task to run on all models. If same model
            is specified in 'models' and 'exclude_models', we exclude this
            model.
          exclude_models, a comma separated list of models not to run this task
            on. Default is None, which allows this task to run on all models.
          any_model, set to True to not pass the model parameter and allow
            a test suite to run any/all models available for testing.
          priority, the string name of a priority from constants.Priorities.
          timeout, the max lifetime of the suite in hours.
          cros_build_spec, spec used to determine the ChromeOS build to test
            with a firmware build, e.g., tot, R41 etc.
          firmware_rw_build_spec, spec used to determine the firmware RW build
            test with a ChromeOS build.
          firmware_ro_build_spec, spec used to determine the firmware RO build
            test with a ChromeOS build.
          firmware_ro_version, pinned firmware RO version.
          firmware_rw_version, pinned firmware RW version.
          test_source, the source of test code when firmware will be updated in
            the test. The value can be 'firmware_rw', 'firmware_ro' or 'cros'.
          job_retry, set to True to enable job-level retry. Default is False.
          no_delay, set to True to raise the priority of this task in task.
          force, set to True to schedule this suite no matter whether there's
            duplicate jobs before.
          queue, so the suite jobs can start running tests with no waiting.
          hour, an integer specifying the hour that a nightly run should be
            triggered, default is set to 21.
          day, an integer specifying the day of a week that a weekly run should
            be triggered, default is set to 5 (Saturday).
          os_type, type of OS, e.g., cros, brillo, android. Default is cros.
            The argument is required for android/brillo builds.
          launch_control_branches, comma separated string of launch control
            branches. The argument is required and only applicable for
            android/brillo builds.
          launch_control_targets, comma separated string of build targets for
            launch control builds. The argument is required and only
            applicable for android/brillo builds.
          testbed_dut_count, number of duts to test when using a testbed.
          qs_account, quota account for the unmanaged pool which has enabled
            Quota Scheduler.
          multi_dut_boards, a common separated list of strings to specify
            board family in a multi-DUTs testing. Each string contains two
            or more boards that separated by semicolon, where the first board
            will be treated as primary board while the rest are secondaries.
            If this args is not None then multi_dut_models args will be
            ignored as they cannot be used together.
          multi_dut_models, a common separated list of strings to specify
            models of DUTs expected in a multi-DUTs testing. Each string
            contains two or more models that separated by semicolon, where the
            first model will be treated as primary model while the rest are
            secondaries.
          multi_dut_trigger, a string to specify how should we trigger a
            multi-DUTs testing. E.g. 'primary': when the primary board has
            a new build, or 'all': when primary and all secondary has a new
            build.

      board_family_config: A board family dictionary mapping board_family name
        to its corresponding boards.
      tot: The tot manager for checking ToT. If it's None, a new tot_manager
        instance will be initialized.
      is_sanity: A boolean; true if we are running in sanity env.
    """
    # Indicate whether there're suites get pushed into taskqueue for this task.
    self.is_pushed = False

    self.analytics_name = task_info.analytics_name
    self.branch_specs = task_info.branch_specs
    self.cros_build_spec = task_info.cros_build_spec
    self.day = task_info.day
    self.firmware_ro_build_spec = task_info.firmware_ro_build_spec
    self.firmware_rw_build_spec = task_info.firmware_rw_build_spec
    self.firmware_ro_version = task_info.firmware_ro_version
    self.firmware_rw_version = task_info.firmware_rw_version
    self.force = task_info.force
    self.frontdoor = task_info.frontdoor
    self.hour = task_info.hour
    self.job_retry = task_info.job_retry
    self.name = task_info.name
    self.no_delay = task_info.no_delay
    self.num = task_info.num
    self.only_hwtest_sanity_required = task_info.only_hwtest_sanity_required
    self.os_type = task_info.os_type
    self.pool = task_info.pool
    self.priority = task_info.priority
    self.qs_account = task_info.qs_account
    self.suite = task_info.suite
    self.test_source = task_info.test_source
    self.testbed_dut_count = task_info.testbed_dut_count
    self.timeout = task_info.timeout
    self.multi_dut_trigger = task_info.multi_dut_trigger

    if task_info.lc_branches:
      self.launch_control_branches = [
          t.strip() for t in task_info.lc_branches.split(',')]
    else:
      self.launch_control_branches = []

    if task_info.lc_targets:
      self.launch_control_targets = [
          t.strip() for t in task_info.lc_targets.split(',')]
    else:
      self.launch_control_targets = []

    if task_info.boards:
      self.boards = [t.strip() for t in task_info.boards.split(',')]
    else:
      self.boards = []

    if task_info.exclude_boards:
      self.exclude_boards = [
          t.strip() for t in task_info.exclude_boards.split(',')]
    else:
      self.exclude_boards = []

    if task_info.models:
      self.models = [t.strip() for t in task_info.models.split(',')]
    else:
      self.models = []

    if task_info.exclude_models:
      self.exclude_models = [
          t.strip() for t in task_info.exclude_models.split(',')]
    else:
      self.exclude_models = []

    self.any_model = task_info.any_model

    if task_info.board_families:
      # Finetune the allowed boards list with board_families & boards.
      families = [family.strip()
                  for family in task_info.board_families.split(',')]
      for family in families:
        self.boards += board_family_config.get(family, [])

    if task_info.exclude_board_families:
      # Finetune the disallowed boards list with exclude_board_families
      # & exclude_boards.
      families = [family.strip()
                  for family in task_info.exclude_board_families.split(',')]
      for family in families:
        self.exclude_boards += board_family_config.get(family, [])

    if tot is None:
      self.tot_manager = tot_manager.TotMilestoneManager()
    else:
      self.tot_manager = tot

    self.dimensions = task_info.dimensions

    self._set_spec_compare_info()
    # Sanity test does not have to upload metrics.
    if not is_sanity:
      self.job_section = analytics.ScheduleJobSection(task_info)

    self.is_multi_dut_testing = False
    if task_info.multi_dut_boards:
      self.is_multi_dut_testing = True
      self.multi_dut_boards = [
          t.strip().split(';') for t in task_info.multi_dut_boards.split(',')]
    else:
      self.multi_dut_boards = []

    if task_info.multi_dut_models:
      self.is_multi_dut_testing = True
      self.multi_dut_models = [
          t.strip().split(';') for t in task_info.multi_dut_models.split(',')]
    else:
      self.multi_dut_models = []

  def schedule(self, launch_control_builds, cros_builds_tuple,
               firmware_builds, configs):
    """Schedule the task by its settings.

    Args:
      launch_control_builds: the build dict for Android boards, see
        return value of |get_launch_control_builds|.
      cros_builds_tuple: the two-tuple of build dicts for ChromeOS boards,
        see return value of |get_cros_builds|.
      firmware_builds:  a dict of firmware artifact, see return value of
        |base_event.get_firmware_builds|.
      configs: a config_reader.Configs object.

    Raises:
      SchedulingError: if tasks that should be scheduled fail to schedule.

    Returns:
      A boolean indicator; true if there were any suites related to this
        task which got pushed into the suites queue.
    """
    assert configs.lab_config is not None
    self.is_pushed = False

    branch_builds, relaxed_builds = cros_builds_tuple
    builds_dict = branch_builds
    if self.only_hwtest_sanity_required:
      builds_dict = _split_unibuilds(relaxed_builds, configs)

    # Record all target boards and models into job section.
    lab_config = configs.lab_config
    models_by_board = lab_config.get_cros_model_map() if lab_config else {}
    boards = self.boards if self.boards else lab_config.get_cros_board_list()
    for b in boards:
      if self.exclude_boards and b in self.exclude_boards:
        continue
      self.job_section.add_board(b)
      models = self.models or models_by_board.get(b, [])
      for m in models:
        if m and '%s_%s' % (b, m) not in self.exclude_models:
          self.job_section.add_model(m)

    logging.info('######## Scheduling task %s ########', self.name)
    if self.os_type == build_lib.OS_TYPE_CROS:
      if not builds_dict:
        logging.info('No CrOS build to run, skip running.')
      else:
        self._schedule_cros_builds(builds_dict, firmware_builds, configs)
    else:
      if not launch_control_builds:
        logging.info('No Android build to run, skip running.')
      else:
        self._schedule_launch_control_builds(launch_control_builds)
    upload_result = False
    try:
      upload_result = self.job_section.upload()
    # For any exceptions from BQ, only log it and move on.
    except Exception as e: #pylint: disable=broad-except
      logging.exception(str(e))
    if not upload_result:
      logging.warning('Failed to insert row: %r', self.job_section)
    return self.is_pushed

  def schedule_multi_duts(self, cros_builds_tuple,
                          recent_cros_builds_tuple, configs):
    """Schedule the multi-DUTs task by its settings.

    Args:
      cros_builds_tuple: the two-tuple of build dicts for ChromeOS boards,
        see return value of |get_cros_builds|.
      recent_cros_builds_tuple: Same as cros_builds_tuple, but contains
        build info with a wider time range.
      configs: a config_reader.Configs object.

    Raises:
      SchedulingError: if tasks that should be scheduled fail to schedule.

    Returns:
      A boolean indicator; true if there were any suites related to this
        task which got pushed into the suites queue.
    """
    assert configs.lab_config is not None
    # For multi-DUTs We allow either request by board or request by model,
    # but not both.
    if self.multi_dut_boards and self.multi_dut_models:
      logging.error('Both board and model presented in request but expecting'
                    'only one of them present at a time.')
      return False
    self.is_pushed = False

    branch_builds, relaxed_builds = cros_builds_tuple
    recent_branch_builds, recent_relaxed_builds = recent_cros_builds_tuple
    builds_dict = branch_builds
    recent_builds_dict = recent_branch_builds
    if self.only_hwtest_sanity_required:
      builds_dict = _split_unibuilds(relaxed_builds, configs)
      # We don't need to expand build info to model level as
      # secondary DUTs will have their builds determined by
      # their board name.
      recent_builds_dict = recent_relaxed_builds

    # Record multi-DUTs testing only for primary boards as we're
    # going to have a replacement for SS and analytics layer soon.
    build_targets_dict = self._get_multi_duts_build_targets_dict(configs)
    model_set = set()
    for board, groups in build_targets_dict.items():
      self.job_section.add_board(board)
      for group in groups:
        if group[0].model:
          model_set.add(group[0].model)
    for model in model_set:
      if self.exclude_models and model not in self.exclude_models:
        self.job_section.add_model(model)

    logging.info('######## Scheduling task %s ########', self.name)
    if self.os_type != build_lib.OS_TYPE_CROS:
      logging.info('Multi-DUTs testing only support cros currently.')
      return False
    if not builds_dict:
      logging.info('No CrOS build to run, skip running.')
      return False
    if not recent_builds_dict:
      logging.info('No recent CrOS build for secondary DUTs to run,'
                   ' skip running.')
      return False
    self._schedule_multi_duts_cros_builds(builds_dict,
                                          recent_builds_dict, configs)

    upload_result = False
    try:
      upload_result = self.job_section.upload()
    # For any exceptions from BQ, only log it and move on.
    except Exception as e: #pylint: disable=broad-except
      logging.exception(str(e))
    if not upload_result:
      logging.warning('Failed to insert row: %r', self.job_section)
    return self.is_pushed

  def _model_to_board_dict(self, models_by_board):
    """Build a model to board dict based on model by boards dict."""
    d = {}
    for board, models in models_by_board.items():
      for model in models:
        d[model] = board
    return d

  def _set_spec_compare_info(self):
    """Set branch spec compare info for task for further check."""
    self._bare_branches = []
    self._version_equal_constraint = False
    self._version_gte_constraint = False
    self._version_lte_constraint = False

    if not self.branch_specs:
      # Any milestone is OK.
      self._numeric_constraint = version.LooseVersion('0')
    else:
      self._numeric_constraint = None
      for spec in self.branch_specs:
        if 'tot' in spec.lower():
          # Convert spec >=tot-1 to >=RXX.
          tot_str = spec[spec.index('tot'):]
          spec = spec.replace(
              tot_str, self.tot_manager.convert_tot_spec(tot_str))

        if spec.startswith('>='):
          self._numeric_constraint = version.LooseVersion(
              spec.lstrip('>=R'))
          self._version_gte_constraint = True
        elif spec.startswith('<='):
          self._numeric_constraint = version.LooseVersion(
              spec.lstrip('<=R'))
          self._version_lte_constraint = True
        elif spec.startswith('=='):
          self._version_equal_constraint = True
          self._numeric_constraint = version.LooseVersion(
              spec.lstrip('==R'))
        else:
          self._bare_branches.append(spec)

  def _fits_spec(self, branch):
    """Check if a branch is deemed OK by this task's branch specs.

    Will return whether a branch 'fits' the specifications stored in this task.

    Examples:
    Assuming tot=R40
    t = Task('Name', 'suite', ['factory', '>=tot-1'])
    t._fits_spec('factory')  # True
    t._fits_spec('40')  # True
    t._fits_spec('38')  # False
    t._fits_spec('firmware')  # False

    Args:
      branch: the branch to check.

    Returns:
      True if branch 'fits' with stored specs, False otherwise.
    """
    if branch in build_lib.BARE_BRANCHES:
      return branch in self._bare_branches

    if self._numeric_constraint:
      if self._version_equal_constraint:
        return version.LooseVersion(branch) == self._numeric_constraint
      elif self._version_gte_constraint:
        return version.LooseVersion(branch) >= self._numeric_constraint
      elif self._version_lte_constraint:
        return version.LooseVersion(branch) <= self._numeric_constraint
      else:
        return version.LooseVersion(branch) >= self._numeric_constraint
    else:
      return False

  def _get_firmware_build(self, spec, board, firmware_build_dict, lab_config):
    """Get the firmware build name to test with ChromeOS build.

    Args:
      spec: a string build spec for RO or RW firmware, eg. firmware,
        cros. For RO firmware, the value can also be released_ro_X.
      board: a string board against which this task will run suite job.
      firmware_build_dict:  a dict of firmware artifacts, see return value of
        |base_event.get_firmware_builds|.
      lab_config: a config.LabConfig object, to read lab config file.

    Returns:
      A string firmware build name.

    Raises:
      ValueError: if failing to get firmware from lab config file;
    """
    if not spec or spec == 'stable':
      # TODO(crbug.com/577316): Query stable RO firmware.
      logging.debug('%s RO firmware build is not supported.', spec)
      return None

    try:
      if firmware_build_dict:
        return firmware_build_dict.get((spec, board), None)
      else:
        return None
    except ValueError as e:
      logging.warning('Failed to get firmware from lab config file'
                      'for spec %s, board %s: %s', spec, board, str(e))
      return None

  def _push_suite(
      self,
      task_id=None,
      board=None,
      model=None,
      cros_build=None,
      firmware_rw_build=None,
      firmware_ro_build=None,
      test_source_build=None,
      launch_control_build=None,
      run_prod_code=False,
      secondary_targets=None):
    """Schedule suite job for the task by pushing suites to SuiteQueue.

    Args:
      task_id: the id to track this task in exectuion.
      board: the board against which this suite job run.
      model: the model name for unibuild.
      cros_build: the CrOS build of this suite job.
      firmware_rw_build: Firmware RW build to run this suite job with.
      firmware_ro_build: Firmware RO build to run this suite job with.
      test_source_build: Test source build, used for server-side
        packaging of this suite job.
      launch_control_build: the launch control build of this suite job.
      run_prod_code: If True, the suite will run the test code that lives
        in prod aka the test code currently on the lab servers. If
        False, the control files and test code for this suite run will
        be retrieved from the build artifacts. Default is False.
      secondary_targets: A list of BuildTarget namedtuple to represent
        required secondary DUTs info in this suite job run.
    """
    android_build = None
    testbed_build = None

    if self.testbed_dut_count:
      launch_control_build = '%s#%d' % (launch_control_build,
                                        self.testbed_dut_count)
      test_source_build = launch_control_build
      board = '%s-%d' % (board, self.testbed_dut_count)

    if launch_control_build:
      if not self.testbed_dut_count:
        android_build = launch_control_build
      else:
        testbed_build = launch_control_build

    if secondary_targets:
      secondary_targets = convert_secondary_targets_to_string(secondary_targets)
    else:
      secondary_targets = ''

    suite_job_parameters = {
        build_lib.BuildVersionKey.ANDROID_BUILD_VERSION: android_build,
        build_lib.BuildVersionKey.CROS_VERSION: cros_build,
        build_lib.BuildVersionKey.FW_RO_VERSION: firmware_ro_build,
        build_lib.BuildVersionKey.FW_RW_VERSION: firmware_rw_build,
        build_lib.BuildVersionKey.TESTBED_BUILD_VERSION: testbed_build,
        'analytics_name': self.analytics_name,
        'board': board,
        'dimensions': self.dimensions,
        'force': self.force,
        'job_retry': self.job_retry,
        'max_runtime_mins': _JOB_MAX_RUNTIME_MINS_DEFAULT,
        'model': model,
        'name': self.name,
        'no_delay': self.no_delay,
        'no_wait_for_results': not self.job_retry,
        'num': self.num,
        'pool': self.pool,
        'priority': self.priority,
        'qs_account': self.qs_account,
        'run_prod_code': run_prod_code,
        'secondary_targets': secondary_targets,
        'suite': self.suite,
        'task_id': task_id,
        'test_source_build': test_source_build,
        'timeout': self.timeout,
        'timeout_mins': _JOB_MAX_RUNTIME_MINS_DEFAULT,
    }

    task_executor.push(task_executor.SUITES_QUEUE,
                       tag=self.suite,
                       **suite_job_parameters)
    logging.info('Pushing task %r into taskqueue', suite_job_parameters)
    self.is_pushed = True

  def _schedule_cros_builds(self, build_dict, firmware_build_dict, configs):
    """Schedule tasks with branch builds.

    Args:
      build_dict: the build dict for ChromeOS boards, see return
        value of |build_lib.get_cros_builds|.
      firmware_build_dict:  a dict of firmware artifact, see return value of
        |base_event.get_firmware_builds|.
      configs: A config_reader.Configs object.
    """
    lab_config = configs.lab_config
    models_by_board = lab_config.get_cros_model_map() if lab_config else {}
    model_agnostic_cros_builds = set()
    for (board, passed_model, build_type,
         milestone), manifest in build_dict.iteritems():
      cros_build = str(build_lib.CrOSBuild(board, build_type, milestone,
                                           manifest))
      logging.info('Running %s on %s', self.name, cros_build)
      if self.exclude_boards and board in self.exclude_boards:
        logging.debug('Board %s is in excluded board list: %s',
                      board, self.exclude_boards)
        continue

      if self.boards and board not in self.boards:
        logging.debug('Board %s is not in supported board list: %s',
                      board, self.boards)
        continue

      # Check the fitness of the build's branch for task
      branch_build_spec = _pick_branch(build_type, milestone)
      if not self._fits_spec(branch_build_spec):
        msg = ("branch_build spec %s doesn't fit this task's "
               "requirement: %s") % (branch_build_spec,
                   ",".join(self.branch_specs))
        logging.debug(msg)
        self.job_section.add_schedule_job(board, passed_model, msg=msg)
        continue

      # Record this build as it matches both board and branch specs.
      if self.only_hwtest_sanity_required:
        self.job_section.add_matched_relax_build(
            board, build_type, milestone, manifest)
      else:
        self.job_section.add_matched_build(
            board, build_type, milestone, manifest)

      # check that we only got one spec for ro firmware
      if all([self.firmware_ro_version, self.firmware_ro_build_spec]):
        logging.error(
          "Exactly one of firmware_ro_version or firmware_ro_build_spec " \
          "allowed, got: %s and %s" % (
            self.firmware_ro_version,
            self.firmware_ro_build_spec,
          ),
        )
        continue

      # check that we only got one spec for rw firmware
      if all([self.firmware_rw_version, self.firmware_rw_build_spec]):
        logging.error(
          "Exactly one of firmware_rw_version or firmware_rw_build_spec " \
          "allowed, got: %s and %s" % (
            self.firmware_rw_version,
            self.firmware_rw_build_spec,
          ),
        )
        continue

      # resolve ro firmware version to provision
      firmware_ro_build = None
      if self.firmware_ro_version:
        firmware_ro_build = self.firmware_ro_version
      elif self.firmware_ro_build_spec:
        firmware_ro_build = self._get_firmware_build(
          self.firmware_ro_build_spec, board, firmware_build_dict, lab_config)

        if not firmware_ro_build:
          msg = 'No RO firmware build to run, skip running'
          logging.debug(msg)
          self.job_section.add_schedule_job(board, passed_model, msg=msg)
          continue

      # resolve rw firmware version to provision
      firmware_rw_build = None
      if self.firmware_rw_version:
        firmware_rw_build = self.firmware_rw_version
      elif self.firmware_rw_build_spec:
        firmware_rw_build = self._get_firmware_build(
          self.firmware_rw_build_spec, board, firmware_build_dict, lab_config)

        if not firmware_rw_build:
          msg = 'No RW firmware build to run, skip running'
          logging.debug(msg)
          self.job_section.add_schedule_job(board, passed_model, msg=msg)
          continue

      if self.test_source == build_lib.BuildType.FIRMWARE_RW:
        test_source_build = firmware_rw_build
      else:
        # Default test source build to CrOS build if it's not specified.
        # Past versions chose based on run_prod_code, but we no longer respect
        # that option and scheduler settings should always set it to False.
        test_source_build = cros_build

      # Record the matched firwmare build.
      if firmware_rw_build:
        self.job_section.add_matched_fw_build(
            board,
            self.firmware_rw_build_spec,
            firmware_rw_build,
            read_only=False)
      if firmware_ro_build:
        self.job_section.add_matched_fw_build(
            board,
            self.firmware_ro_build_spec,
            firmware_ro_build,
            read_only=True)

      # Board above is used as build target to control the CrOS image.
      # The following part is to assign models for lab boards, where
      # the suffix should be removed.
      hwtest_board = build_lib.reshape_board(board)

      models = models_by_board.get(hwtest_board, [None])

      for model in models:
        if ((passed_model is not None and model == passed_model) or
            passed_model is None):
          full_model_name = '%s_%s' % (hwtest_board, model)
          # Respect exclude first.
          if self.exclude_models and full_model_name in self.exclude_models:
            logging.debug("Skip model %s as it's in exclude model list %s",
                          model, self.exclude_models)
            continue

          if self.models and full_model_name not in self.models:
            logging.debug("Skip model %s as it's not in support model list %s",
                          model, self.models)
            continue

          explicit_model = model

          if self.any_model:
            explicit_model = None
            unique_build = str(cros_build)
            if unique_build in model_agnostic_cros_builds:
              # Skip since we've already run with no explicit model set.
              msg = "Skip model %s as any_model enabled for this job." % model
              self.job_section.add_schedule_job(board, model, msg=msg)
              continue
            model_agnostic_cros_builds.add(unique_build)

          task_id = str(uuid.uuid1())
          self._push_suite(
              task_id=task_id,
              board=hwtest_board,
              model=explicit_model,
              cros_build=cros_build,
              firmware_rw_build=firmware_rw_build,
              firmware_ro_build=firmware_ro_build,
              test_source_build=test_source_build)

          # Analytics table stores the build target instead of the lab board.
          self.job_section.add_schedule_job(
              board, explicit_model, task_id=task_id)

  def _schedule_multi_duts_cros_builds(self, build_dict,
                                       recent_build_dict, configs):
    """Schedule multi-DUTs tasks with branch builds.

    Args:
      build_dict: the build dict for ChromeOS boards, see return
        value of |build_lib.get_cros_builds|.
      recent_build_dict: Same as build_dict, but contains build info
        with a wider time range.
      configs: A config_reader.Configs object.
    """
    build_targets_dict = self._get_multi_duts_build_targets_dict(configs)
    model_agnostic_builds = set()
    for (board, passed_model, build_type,
         milestone), manifest in build_dict.iteritems():
      cros_build = str(build_lib.CrOSBuild(board, build_type, milestone,
                                           manifest))
      logging.info('Running %s on %s', self.name, cros_build)
      if board not in build_targets_dict.keys():
        logging.debug('Board %s is not in primary board list: %s',
                      board, build_targets_dict.keys())
        continue

      # Check the fitness of the build's branch for task
      branch_build_spec = _pick_branch(build_type, milestone)
      if not self._fits_spec(branch_build_spec):
        msg = ("branch_build spec %s doesn't fit this task's "
               "requirement: %s") % (branch_build_spec,
                   ",".join(self.branch_specs))
        logging.debug(msg)
        self.job_section.add_schedule_job(board, passed_model, msg=msg)
        continue

      # Record this build as it matches both board and branch specs.
      if self.only_hwtest_sanity_required:
        self.job_section.add_matched_relax_build(
            board, build_type, milestone, manifest)
      else:
        self.job_section.add_matched_build(
            board, build_type, milestone, manifest)

      # Board above is used as build target to control the CrOS image.
      # The following part is to assign models for lab boards, where
      # the suffix should be removed.
      hwtest_board = build_lib.reshape_board(board)
      for group in build_targets_dict.get(board):
        joined_board_strings = '_'.join(dut.board for dut in group)
        build_tag = '%s_%s' % (joined_board_strings, cros_build)
        primary_dut = group[0]
        if primary_dut.model:
          if primary_dut.model != passed_model:
            # Explict model specified but not match, so skip to next.
            continue
        elif build_tag in model_agnostic_builds:
          msg = ("Skip model %s as any_model enabled for this job."
                % passed_model)
          self.job_section.add_schedule_job(board, passed_model, msg=msg)
          continue

        # Determine cros builds for secondary DUTs from recent build dict.
        secondary_targets = []
        for s_dut in group[1:]:
          s_key = (s_dut.board, None, build_type, milestone)
          s_manifest = recent_build_dict.get(s_key, '')
          if s_manifest:
            s_cros_build = str(build_lib.CrOSBuild(
                s_dut.board, build_type, milestone, s_manifest))
            s_hwtest_board = build_lib.reshape_board(s_dut.board)
            secondary_targets.append(
                BuildTarget(s_hwtest_board, s_dut.model, s_cros_build))
        # Check if we get cros build for all secondary DUTs.
        if len(secondary_targets) != len(group[1:]):
          logging.info('Cannot determine cros version for all secondary'
                       ' DUTs, skip.')
          continue

        # Schedule task.
        model_agnostic_builds.add(build_tag)
        task_id = str(uuid.uuid1())
        self._push_suite(
          task_id = task_id,
          board=hwtest_board,
          model=primary_dut.model,
          cros_build=cros_build,
          test_source_build=cros_build,
          secondary_targets=secondary_targets
        )

        # Analytics table stores the build target instead of the lab board.
        self.job_section.add_schedule_job(
            board, primary_dut.model, task_id=task_id)

  def _schedule_launch_control_builds(self, launch_control_builds):
    """Schedule tasks with launch control builds.

    Args:
      launch_control_builds: the build dict for Android boards.
    """
    for board, launch_control_build in launch_control_builds.iteritems():
      logging.debug('Running %s on %s', self.name, board)
      if self.exclude_boards and board in self.exclude_boards:
        logging.debug('Board %s is in excluded board list: %s',
                      board, self.exclude_boards)
        continue
      if self.boards and board not in self.boards:
        logging.debug('Board %s is not in supported board list: %s',
                      board, self.boards)
        continue

      for android_build in launch_control_build:
        if not any([branch in android_build
                    for branch in self.launch_control_branches]):
          logging.debug('Branch %s is not required to run for task '
                        '%s', android_build, self.name)
          continue

        self._push_suite(board=board,
                         test_source_build=android_build,
                         launch_control_build=android_build)

  def _get_multi_duts_build_targets_dict(self, configs):
    """Generate a dict contains all build targets info based on
    self.multi_dut_boards or self.multi_dut_models.

    Args:
      configs: A config_reader.Configs object.

    Returns:
      A dict where key is a cros board, and value is a list that represents
      group of DUTs where primary DUT's board equal to key. Each group of
      DUTs are represented by a list of BuildTarget. Example:
      {
        'coral': [
          [
            BuildTarget(board='coral', model='babytiger', cros_build=None),
            BuildTarget(board='eve', model=None, cros_build=None),
            BuildTarget(board='nami', model='None', cros_build=None)
          ],
          [
            BuildTarget(board='coral', model='blacktiplte', cros_build=None),
            BuildTarget(board='octopus', model=None, cros_build=None),
            BuildTarget(board='nami', model=None, cros_build=None)],
          ]
        ]
      }
    """
    lab_config = configs.lab_config
    build_targets = defaultdict(lambda: [])
    models_by_board = lab_config.get_cros_model_map() if lab_config else {}
    model_to_board_dict = self._model_to_board_dict(models_by_board)
    # Handle the case when multi-DUTs testing requested by board.
    for group in self.multi_dut_boards:
      primary_board = group[0]
      if self.any_model:
        new_group = [BuildTarget(board, None, None) for board in group]
        build_targets[primary_board].append(new_group)
      else:
        # If any_model disbled, we need to have each model from primary_board
        # family pair with requested secondary devices.
        # Board above is used as build target to control the CrOS image.
        # The following part is to assign models for lab boards, where
        # the suffix should be removed.
        hwtest_board = build_lib.reshape_board(primary_board)
        models = models_by_board.get(hwtest_board, [None])
        for model in models:
          if self.exclude_models and model in self.exclude_models:
            logging.info('Model %s is in exclude list, skipping.' % model)
            continue
          new_group = []
          new_group.append(BuildTarget(primary_board, model, None))
          for board in group[1:]:
            new_group.append(BuildTarget(board, None, None))
          build_targets[primary_board].append(new_group)
    # Handle the case when multi-DUTs testing requested by model.
    for group in self.multi_dut_models:
      boards = [model_to_board_dict.get(model, '') for model in group]
      if '' in boards:
        logging.info('Cannot find board name from one of requested model,'
                     ' skipping.')
        continue
      new_group = [BuildTarget(boards[i], group[i], None) for i in range(len(group))]
      build_targets[boards[0]].append(new_group)
    return build_targets


def _pick_branch(build_type, milestone):
  """Select branch based on build type.

  If the build_type is a bare branch, return build_type as the build spec.
  If the build_type is a normal CrOS branch, return milestone as the build
  spec.

  Args:
    build_type: a string builder name, like 'release'.
    milestone: a string milestone, like '55'.

  Returns:
    A string milestone if build_type represents CrOS build, otherwise
    return build_type.
  """
  return build_type if build_type in build_lib.BARE_BRANCHES else milestone


def _split_unibuilds(build_dict, configs):
  """Split the uni-builds to all models under a board.

  Args:
    build_dict: the build dict for ChromeOS boards, see return
      value of |build_lib.get_cros_builds|.
    configs: a config_reader.Configs object.

  Returns:
    A build dict.
  """
  models_by_board = configs.lab_config.get_cros_model_map()
  if not models_by_board:
    return build_dict
  all_branch_build_dict = {}
  for (board, model, config, milestone), platform in build_dict.iteritems():
    uni_build_models = models_by_board.get(board)
    if uni_build_models is not None and model is None:
      for uni_build_model in uni_build_models:
        model_key = (board, uni_build_model, config, milestone)
        _add_build_dict(all_branch_build_dict, model_key, platform)
      continue
    build_key = (board, model, config, milestone)
    _add_build_dict(all_branch_build_dict, build_key, platform)

  return all_branch_build_dict


def _add_build_dict(build_dict, key, value):
  """A wrapper to add or update an item in build_dict."""
  cur_manifest = build_dict.get(key)
  if cur_manifest is None:
    build_dict[key] = value
    return
  build_dict[key] = max(
      [cur_manifest, value], key=version.LooseVersion)

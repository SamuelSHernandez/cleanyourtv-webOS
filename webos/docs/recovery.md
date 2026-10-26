# Recovery

## If something is wrong right now

| Situation | Do this |
|---|---|
| Home keeps opening the launcher and you want LG Home | Press Home again within 3 seconds of the launcher appearing: LG Home stays until you open another app. To stop routing for good: `webos/cytv-webos home stop --device tv`. |
| The computer running the watcher is off, asleep or gone | Nothing to do: without the watcher, Home is LG Home. The watcher is the only thing that routes Home in this release. |
| The launcher shows no apps, or apps it cannot open | Use LG's app bar as usual. Then run `cytv-webos sync`, `cytv-webos build --device tv` and `cytv-webos install --device tv`. |
| You want everything gone | `webos/cytv-webos restore --device tv`. It stops Home routing first, then removes the apps this tool installed (add-ons first, the launcher last), and checks each one is gone. |
| You want one add-on gone | `webos/cytv-webos addon remove --device tv <its app id>`; the launcher stays. |
| `restore` printed `recovery_incomplete` or `unknown` | Wait until the TV is on and Developer Mode is active, then run `cytv-webos status --device tv`, which settles the outcome by reading the TV. Then run `restore` again. |
| Developer Mode expired | The TV has already removed the launcher. LG Home works as normal. The watcher, if running, moves to `failed`. Renew Developer Mode in LG's Developer Mode app, then `install` again. |

This release changes no system setting, system service or system file on the TV. It installs Developer Mode
apps (the launcher and any add-ons you choose). LG Home stays installed and reachable throughout.

## What is recorded, and where

Everything lives on the computer under `~/.cleanyourtv-webos/<device>/` (or `$CYTV_WEBOS_HOME`). The folder is
mode 0700 and each file is 0600.

| File | Holds | Written |
|---|---|---|
| `journal.json` | The baseline (model, SDK and firmware, and for each app id whether it was already there); each operation with exactly one outcome; the apps this tool owns and their role (launcher or add-on); readiness |
| `cards.json` | Your card decisions (show or hide) for add-ons, with the package SHA-256 you approved |
| `device.json` | The TV's address and the theme folder it was last installed with | The baseline once, before the first change. The intent before each change. The outcome after reading the result back. |
| `integration.json` | The Home state machine: backend, state, reason, last 20 transitions | On every transition |
| `ssap-credentials.json` | The SSAP client key and the TV certificate's SHA-256 | When pairing. It is never printed, and never part of `check` output. |
| `inventory/` | The TV's app list and icons, for the next build | When you run `sync` |

Writes go to a new temporary file in the same folder. The file is flushed and fsynced, renamed into place, and the
folder is fsynced too. That protects against a half-written record after a crash. It does not prove a record
survives a power cut on every disk, because some disks acknowledge fsync early. A record that does not parse,
or comes from another format version, is never repaired or replaced: the tool stops and says which file to
move aside.

## Outcomes

| Outcome | Meaning |
|---|---|
| `not_attempted` | Nothing was sent |
| `refused` | A check said no before anything changed, or the TV refused the session (Developer Mode key) |
| `failed` | Sent, and read back as not done |
| `applied_verified` | Sent, and read back as done (app id and version listed by the TV) |
| `unknown` | Sent, and the link dropped before the result could be read. `install`, `restore` and `status` reconcile it first and send nothing new until they can. While it is open, `confirm-ready` refuses, the launcher counts as not ready, `home enable` refuses, and a running watcher moves to `failed` before its next launch. |
| `restored_verified` | Removal read back as absent |
| `recovery_incomplete` | Removal read back as still present, or the app existed before this tool installed over it |

Exit codes: 0 for done and verified, 1 for refused or failed, 2 for unknown or incomplete.

## Home integration states

```
inactive --enable--> activating --redirect confirmed--> active
   ^                     |  \--lost--> unknown --TV answers--> activating
   |                     +--------- fail ------> failed --resume--+
   +------------------------------------------- resume -----------+
any state --stop--> stopped --resume--> inactive
```

- `enable` needs the launcher's readiness confirmed by a person, for the installed version.
- `enable` refuses when another Home controller or a root setup is installed.
- A watcher acts only in `activating` or `active`. It re-reads the record once a second and immediately
  before every launch.
- Nothing leaves `stopped` or `failed` except `cytv-webos home resume`, and the watcher never calls it.

## Failure boundary of the external watcher

The watcher is a process on the computer that reads the foreground app over SSAP and sends one kind of
command: launch this launcher. It never touches the TV's input devices, so a hang or crash cannot hold the
remote. The TV simply behaves as stock. The emergency gesture (a second Home press) is handled by the watcher,
so it is not the only protection. What bounds the watcher independently of its own judgement:

- **Persistent stop.** `home stop` writes to the record, not to the watcher, so it works even when the watcher
  is unresponsive. A watcher started later by a supervisor reads `stopped` and exits.
- **Caps on each kind of runaway:**
  - 5 redirects a minute;
  - 2 launches in a row that never reach the front;
  - 5 process starts in 10 minutes.

  Past any cap the record moves to `failed`.
- **Physical last resort.** Stopping the computer, its network, or the TV's network leaves LG Home in charge.

## Invariants and the tests that hold them

| # | Invariant | How | Test |
|---|---|---|---|
| 1 | No integration before the launcher shows readiness | `home enable`, and every watcher launch, need readiness confirmed by a person for the installed version. A new install clears it. | `test_cli.test_install_status_restore`, `test_home.EnableTest`, `test_a_new_unconfirmed_install_stops_routing_before_the_next_launch`, `test_an_install_during_the_question_is_not_overwritten` |
| 2 | Readiness and Home routing verified separately | Readiness: a person, recorded in the journal. Routing: the launcher seen in front after a redirect (`activating` to `active`). | `test_lifecycle.test_launch_acknowledged_but_not_running_or_ready`, `test_home.test_redirect_confirms_activation` |
| 3 | LG Home stays recoverable | Nothing on the TV is changed. Passthrough. `home stop`. `restore`. | `test_home.test_second_home_press_right_after_a_redirect_stays_on_lg_home`, `test_stop_written_while_running_is_obeyed_before_the_next_launch` |
| 4 | Exactly one Home owner | One backend field. Activation refused while another backend or controller is present. | `test_one_backend_at_a_time`, `test_another_home_controller_blocks_activation` |
| 5 | Emergency stop survives restarts, not undone by a watchdog | The stop is a file the watcher reads and never clears. Transitions are locked, so a watcher's transition cannot overwrite a concurrent stop. `restore` writes the stop before anything that can fail. | `test_a_restarted_watcher_does_not_undo_a_stop`, `test_stop_persists_and_only_resume_leaves_it`, `test_stop_and_a_watcher_transition_cannot_interleave`, `test_refused_restore_still_stops_home_routing` |
| 6 | Explicit action to resume | Only `resume` leaves `stopped`/`failed` | `test_cli.test_home_stop_and_resume_are_explicit` |
| 7 | A hung helper cannot hold the remote | The watcher has no input access: only list, foreground and launch | `test_home.WatcherReachTest` |
| 8 | Grabs and forwarded keys released | Not applicable: no input is grabbed in this release | (hardware gate for any future helper) |
| 9 | Other buttons, long presses and repeats unaffected | The launcher handles only arrows, OK and Back. The watcher ignores every app but LG Home. | `logic.test.js` "arrow repeats…", `test_unrelated_apps_and_settings_are_never_redirected` |
| 10 | Bounded recovery, no restart loops | Redirect, confirm and start caps; backoff up to 60 s. Locks are released by the kernel when a process dies, so a crash leaves no stale lock (POSIX). | `test_redirect_storm_is_bounded`, `test_restart_loop_is_bounded`, `test_unreachable_tv_backs_off_without_failing`, `test_a_crashed_holder_leaves_no_stale_lock` |
| 11 | Retries keep the original baseline | The baseline is written once | `test_rejected_installation_fails_without_launch_and_keeps_baseline_for_retry` |
| 12 | A failed restore is never reported as success | Read back after removal; `recovery_incomplete`, exit 2 | `test_failed_removal_is_never_reported_as_restored`, `test_cli.test_failed_restore_exits_2_and_says_incomplete` |
| 13 | Lost link after a mutation is unknown until reconciled | `unknown` outcome, reconciled before anything new is sent. An update that never landed reconciles to `failed`. Nothing counts as ready while an outcome is open. | `test_link_lost_after_install_is_unknown_until_reconciled`, `test_update_that_never_landed_reconciles_to_failed_and_unblocks`, `test_link_lost_during_removal_is_unknown_then_reconciled`, `test_link_lost_after_launch_is_unknown_then_reconciled_back_to_activating`, `test_an_open_operation_is_not_ready` |
| 14 | Back to LG Home restores what LG Home needs | Not applicable: no cleanup exists in this release | (gate for the root tier) |
| 15 | Uninstall removes only what this tool owns | Install accepts only the launcher's own id, and only over the app the journal owns. Restore removes the journal's owned app only. Without a journal, nothing. An adopted copy is kept. | `test_a_package_with_another_app_id_is_refused`, `test_restore_only_touches_its_own_app`, `test_without_a_journal_nothing_is_invented`, `test_app_installed_by_something_else_is_refused_then_adopted_and_kept_on_restore` |

All of these run against simulated TVs. [hardware-acceptance.md](hardware-acceptance.md) lists what only a real
TV can show.

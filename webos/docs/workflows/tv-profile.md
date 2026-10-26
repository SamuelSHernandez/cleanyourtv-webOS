# Workflow: Record a TV in a profile

**When to use this:** the launcher ran on a TV, or failed to, and others should know.

1. Run the parts of [`../hardware-acceptance.md`](../hardware-acceptance.md) you can, on the real TV, with the
   remote.
2. Add an entry to `evidence` in the matching profile under `profiles/`:
   - `model`, `firmware`, `sdk` (from `cytv-webos check`);
   - `app_version`, `backend`, `date`, `checklist` (which sections passed) and `notes`.
3. Pick the honest level:
   - `experimental-hardware`: a developer of this project, partial checklist;
   - `community-reported`: your full run;
   - `maintainer-verified`: a maintainer's run;
   - `known-incompatible`: it fails, and how.

   A backend's `evidence` field may claim a level only if an entry at that level exists.
4. No serial numbers, MAC or IP addresses, Wi-Fi names or account names: the model, firmware and SDK are enough.

Then run the tests: `test_package.ProfileTest` validates every entry.

# Repoman™, the simple repository manager

Repoman is a fusion of [repository-timeline](https://github.com/desyops/repository-timeline) and [upstream_sync](https://github.com/pyther/upstream_sync), enabling lightweight RPM repository management with a bit nicer UI

## Why?

Because Katello is *way* too much

## What can it do

For now, it can:
  - Mirror repositories using reposync
  - Manage snapshots
  - Use Red Hat entitlement certificates to download packages from Red Hat CDN (Note: Make sure you are compliant with licensing)
  
I recommend you use `--help` a lot

## Configuration

See the example configuration file for available options. The system is intended to be mostly self-documenting (that is, I am too lazy to write a proper manual at this point :-))

## Using snapshots

The timeline logic remains similar to the source project. A snapshot is merely a recursive copy of the source directory using hard links and some special logic to handle repository metadata that can't be hardlinked. For this reason, snapshots and sources can't cross filesystem boundaries.

After you create your first timeline (if named 'default', it becomes the default timeline when nothing is specified), you can use the `snapshot-create` command to create snapshots. You can create auto-rotating "unnamed" snapshots or named snapshots, and dynamically-updatable links to them.

## Does this actually work?

Maybe. If it doesn't, fix it and send a patch, or open an issue.


## TODO:

Lots. Not everything in the UI is actually implemented yet.
I would also like to integrate mergerepo with this tool.

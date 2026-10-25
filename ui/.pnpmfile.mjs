// Wires the @pnpm/plugin-esm-node-path config dependency into pnpm.
//
// This project uses a global virtual store (see pnpm-workspace.yaml). With
// that store, dependencies are symlinked from outside the project, so pnpm
// adds the hoisted node_modules/.pnpm/node_modules dir to NODE_PATH. Node's
// CommonJS loader honors NODE_PATH, but ESM does not — so the plugin's
// updateConfig hook registers an ESM loader (via NODE_OPTIONS) that restores
// NODE_PATH resolution. Config dependencies are installed before this file is
// loaded, so the import below resolves to node_modules/.pnpm-config/...
//
// NOTE: keep this file committed. The lockfile records its checksum
// (pnpmfileChecksum), so a missing .pnpmfile.mjs breaks `pnpm exec`.
import plugin from './node_modules/.pnpm-config/@pnpm/plugin-esm-node-path/pnpmfile.cjs'

export const hooks = plugin.hooks

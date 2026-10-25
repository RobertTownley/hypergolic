export interface TreeFile {
  path: string;
  status: string;
  additions: number;
  deletions: number;
}

export interface FileTreeNode {
  name: string;
  path: string;
  children: Map<string, FileTreeNode>;
  file?: TreeFile;
  untrackedPath?: string;
}

function insertLeaf(root: FileTreeNode, path: string): FileTreeNode {
  const parts = path.split("/");
  let current = root;
  for (let i = 0; i < parts.length - 1; i++) {
    const dir = parts[i];
    if (!current.children.has(dir)) {
      current.children.set(dir, {
        name: dir,
        path: parts.slice(0, i + 1).join("/"),
        children: new Map(),
      });
    }
    current = current.children.get(dir)!;
  }
  const fileName = parts[parts.length - 1];
  const leaf: FileTreeNode = { name: fileName, path, children: new Map() };
  current.children.set(fileName, leaf);
  return leaf;
}

export function buildTree(files: TreeFile[], untrackedPaths: string[]): FileTreeNode {
  const root: FileTreeNode = { name: "", path: "", children: new Map() };
  for (const file of files) insertLeaf(root, file.path).file = file;
  for (const uPath of untrackedPaths) insertLeaf(root, uPath).untrackedPath = uPath;
  return root;
}

export function getAllPaths(node: FileTreeNode): string[] {
  const paths: string[] = [];
  for (const child of node.children.values()) {
    if (child.file) paths.push(child.file.path);
    if (child.untrackedPath) paths.push(child.untrackedPath);
    paths.push(...getAllPaths(child));
  }
  return paths;
}

export function sortedChildren(node: FileTreeNode): FileTreeNode[] {
  return Array.from(node.children.values()).sort((a, b) => {
    const aIsDir = a.children.size > 0 && !a.file && !a.untrackedPath;
    const bIsDir = b.children.size > 0 && !b.file && !b.untrackedPath;
    if (aIsDir && !bIsDir) return -1;
    if (!aIsDir && bIsDir) return 1;
    return a.name.localeCompare(b.name);
  });
}

// File paths in the visual order TreeSection renders them (dirs first, sorted)
export function orderedFilePaths(node: FileTreeNode): string[] {
  const paths: string[] = [];
  for (const child of sortedChildren(node)) {
    if (child.file) paths.push(child.file.path);
    else if (child.untrackedPath) paths.push(child.untrackedPath);
    else paths.push(...orderedFilePaths(child));
  }
  return paths;
}

export function collectDirPaths(node: FileTreeNode): string[] {
  const paths: string[] = [];
  for (const child of node.children.values()) {
    const isDir = child.children.size > 0 && !child.file && !child.untrackedPath;
    if (isDir) {
      paths.push(child.path);
      paths.push(...collectDirPaths(child));
    }
  }
  return paths;
}

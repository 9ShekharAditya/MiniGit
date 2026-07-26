import sys
import os
import hashlib
import zlib
import time
import difflib

MINIGIT_DIR = ".minigit"


# ---------- Object storage (blobs, trees, commits all use this) ----------

def hash_data(data, obj_type="blob", store=True):
    header = f"{obj_type} {len(data)}\0".encode()
    full_data = header + data
    sha1_hash = hashlib.sha1(full_data).hexdigest()

    if store:
        dir_name = sha1_hash[:2]
        file_name = sha1_hash[2:]
        object_dir = os.path.join(MINIGIT_DIR, "objects", dir_name)
        os.makedirs(object_dir, exist_ok=True)
        compressed = zlib.compress(full_data)
        with open(os.path.join(object_dir, file_name), "wb") as f:
            f.write(compressed)

    return sha1_hash


def read_object(sha1_hash):
    dir_name = sha1_hash[:2]
    file_name = sha1_hash[2:]
    path = os.path.join(MINIGIT_DIR, "objects", dir_name, file_name)

    with open(path, "rb") as f:
        compressed = f.read()

    full_data = zlib.decompress(compressed)
    null_index = full_data.index(b"\0")
    header = full_data[:null_index].decode()
    content = full_data[null_index + 1:]

    obj_type, _size = header.split(" ")
    return obj_type, content


# ---------- init ----------

def cmd_init():
    os.makedirs(os.path.join(MINIGIT_DIR, "objects"), exist_ok=True)
    os.makedirs(os.path.join(MINIGIT_DIR, "refs", "heads"), exist_ok=True)

    with open(os.path.join(MINIGIT_DIR, "HEAD"), "w") as f:
        f.write("ref: refs/heads/main\n")

    index_path = os.path.join(MINIGIT_DIR, "index")
    if not os.path.exists(index_path):
        open(index_path, "w").close()

    print("Initialized empty minigit repository")


# ---------- hash-object / cat-file ----------

def hash_object(filepath, store=True):
    with open(filepath, "rb") as f:
        content = f.read()
    return hash_data(content, "blob", store)


def cmd_hash_object(args):
    print(hash_object(args[0]))


def cmd_cat_file(args):
    _obj_type, content = read_object(args[0])
    sys.stdout.buffer.write(content)


# ---------- index (staging area) ----------

def read_index():
    index_path = os.path.join(MINIGIT_DIR, "index")
    entries = {}
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                sha1_hash, path = line.split(" ", 1)
                entries[path] = sha1_hash
    return entries


def write_index(entries):
    index_path = os.path.join(MINIGIT_DIR, "index")
    with open(index_path, "w") as f:
        for path in sorted(entries):
            f.write(f"{entries[path]} {path}\n")


def cmd_add(args):
    filepath = args[0]
    sha1_hash = hash_object(filepath, store=True)

    entries = read_index()
    entries[filepath] = sha1_hash
    write_index(entries)

    print(f"Added {filepath} ({sha1_hash})")


# ---------- tree objects ----------

def write_tree():
    entries = read_index()
    lines = []
    for path in sorted(entries):
        lines.append(f"blob {entries[path]} {path}")
    tree_content = "\n".join(lines).encode()
    return hash_data(tree_content, "tree", store=True)


def cmd_write_tree(args):
    print(write_tree())


def read_tree(tree_hash):
    """Returns dict {path: blob_hash} for a tree object."""
    _obj_type, content = read_object(tree_hash)
    entries = {}
    for line in content.decode().splitlines():
        if not line.strip():
            continue
        _kind, blob_hash, path = line.split(" ", 2)
        entries[path] = blob_hash
    return entries


# ---------- refs / HEAD ----------

def get_current_branch_ref():
    with open(os.path.join(MINIGIT_DIR, "HEAD"), "r") as f:
        head = f.read().strip()
    # head looks like: "ref: refs/heads/main"
    ref_path = head.split(" ", 1)[1]
    return ref_path


def get_head_commit():
    ref_path = get_current_branch_ref()
    full_ref_path = os.path.join(MINIGIT_DIR, ref_path)
    if os.path.exists(full_ref_path):
        with open(full_ref_path, "r") as f:
            return f.read().strip()
    return None


def update_head_commit(commit_hash):
    ref_path = get_current_branch_ref()
    full_ref_path = os.path.join(MINIGIT_DIR, ref_path)
    os.makedirs(os.path.dirname(full_ref_path), exist_ok=True)
    with open(full_ref_path, "w") as f:
        f.write(commit_hash + "\n")


# ---------- commit ----------

def cmd_commit(args):
    # usage: minigit commit -m "message"
    message = args[args.index("-m") + 1]

    tree_hash = write_tree()
    parent_hash = get_head_commit()

    lines = [f"tree {tree_hash}"]
    if parent_hash:
        lines.append(f"parent {parent_hash}")
    lines.append(f"author You <you@example.com> {int(time.time())}")
    lines.append("")
    lines.append(message)

    commit_content = "\n".join(lines).encode()
    commit_hash = hash_data(commit_content, "commit", store=True)

    update_head_commit(commit_hash)
    print(f"Committed as {commit_hash}")


def parse_commit(commit_hash):
    _obj_type, content = read_object(commit_hash)
    text = content.decode()
    header_part, message = text.split("\n\n", 1)

    tree_hash = None
    parent_hash = None
    for line in header_part.splitlines():
        if line.startswith("tree "):
            tree_hash = line.split(" ", 1)[1]
        elif line.startswith("parent "):
            parent_hash = line.split(" ", 1)[1]

    return {"tree": tree_hash, "parent": parent_hash, "message": message.strip()}


# ---------- log ----------

def cmd_log(args):
    commit_hash = get_head_commit()
    if not commit_hash:
        print("No commits yet")
        return

    while commit_hash:
        commit = parse_commit(commit_hash)
        print(f"commit {commit_hash}")
        print(f"    {commit['message']}")
        print()
        commit_hash = commit["parent"]


# ---------- diff (basic: compare working file vs last committed version) ----------

def cmd_diff(args):
    filepath = args[0]

    commit_hash = get_head_commit()
    if not commit_hash:
        print("No commits yet to diff against")
        return

    commit = parse_commit(commit_hash)
    tree_entries = read_tree(commit["tree"])

    if filepath not in tree_entries:
        print(f"{filepath} is untracked (not in last commit)")
        return

    old_blob_hash = tree_entries[filepath]
    _obj_type, old_content = read_object(old_blob_hash)
    old_lines = old_content.decode().splitlines(keepends=True)

    with open(filepath, "rb") as f:
        new_lines = f.read().decode().splitlines(keepends=True)

    diff = difflib.unified_diff(old_lines, new_lines, fromfile="committed", tofile="working")
    sys.stdout.writelines(diff)


# ---------- CLI dispatch ----------

def main():
    command = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "init": lambda: cmd_init(),
        "hash-object": lambda: cmd_hash_object(args),
        "cat-file": lambda: cmd_cat_file(args),
        "add": lambda: cmd_add(args),
        "write-tree": lambda: cmd_write_tree(args),
        "commit": lambda: cmd_commit(args),
        "log": lambda: cmd_log(args),
        "diff": lambda: cmd_diff(args),
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
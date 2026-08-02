import sys, os, hashlib, zlib, time

MINIGIT_DIR = ".minigit"

#creating a blob object and storing it in the .minigit/objects directory
def hash_data(data, store=True):
    header = f"blob {len(data)}\0".encode()
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

#reading the blob object from the .minigit/objects directory and returning the content of the file
def read_data(sha1_hash):
    dir_name = sha1_hash[:2]
    file_name = sha1_hash[2:]
    path = os.path.join(MINIGIT_DIR, "objects", dir_name, file_name)
    with open(path, "rb") as f:
        compressed = f.read()
    full_data = zlib.decompress(compressed)
    null_index = full_data.index(b"\0")
    return full_data[null_index + 1:]

#initializing the minigit repository by creating the necessary directories and files
def cmd_init():
    os.makedirs(os.path.join(MINIGIT_DIR, "objects"), exist_ok=True)
    open(os.path.join(MINIGIT_DIR, "index"), "w").close()
    if not os.path.exists(os.path.join(MINIGIT_DIR, "HEAD")):
        with open(os.path.join(MINIGIT_DIR, "HEAD"), "w") as f:
            f.write("") #empty file creation

    print("Minigit Repo Initialized")

#reading the index file and returning a dictionary of file paths and their corresponding SHA-1 hashes
def read_index():
    entries = {}
    path = os.path.join(MINIGIT_DIR, "index")
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                h, p = line.split(" ", 1)
                entries[p] = h
    return entries

#writing the index file with the updated entries of file paths and their corresponding SHA-1 hashes
def write_index(entries):
    path = os.path.join(MINIGIT_DIR, "index")
    with open(path, "w") as f:
        for p in sorted(entries):
            f.write(f"{entries[p]} {p}\n")

#adding a file to the staging area by reading its content, hashing it, and updating the index file
def cmd_add(filepath):
    with open(filepath, "rb") as f:
        content = f.read() #reading raw bytes from the staged file
    sha1_hash = hash_data(content, store = True) #hash and store conten as blob object 
    entries = read_index()
    entries[filepath] = sha1_hash
    write_index(entries)
    print(f"Added {filepath} -> {sha1_hash}")


#getting the hash of the latest commit from the HEAD file
def get_HEAD(): #getting hash of the lastest commit
    path = os.path.join(MINIGIT_DIR, "HEAD")
    with open(path, "r") as f:
        content = f.read().strip()
    return content if content else None

#setting the hash of the latest commit in the HEAD file
def set_HEAD(commit_hash):
    path = os.path.join(MINIGIT_DIR, "HEAD")
    with open(path, "w") as f:
        f.write(commit_hash)

#creating a commit object with the staged files, parent commit hash, timestamp, and commit message, and storing it in the .minigit/objects directory
def cmd_commit(message):
    entries = read_index() #gets the staged files

    lines = []
    parent = get_HEAD()
    if parent:
        lines.append(f"parent {parent}")
    lines.append(f"time {int(time.time())}")
    lines.append(f"message {message}")
    lines.append("files: ")
    for path in sorted(entries):
        lines.append(f"{entries[path]} {path}")
    commit_content = "\n".join(lines).encode()
    commit_hash = hash_data(commit_content, store = True)

    set_HEAD(commit_hash)
    print(f"Committed as {commit_hash}")

#parsing the commit object to extract the parent commit hash, commit message, and staged files
def parse_commit(commit_hash):
    content = read_data(commit_hash).decode()
    lines = content.splitlines()

    parent = None
    message = ""
    files = {}
    reading_files = False

    for line in lines: 
        if line.startswith("parent "):
            parent = line.split(" ", 1)[1]
        elif line.startswith("message "):
            message = line.split(" ", 1)[1]
        elif line == "files: ":
            reading_files = True
        elif reading_files and line.strip():
            h, p = line.split(" ", 1)
            files[p]=h
    return {"parent": parent, "message": message, "files": files}

#printing the commit history by traversing the commit objects starting from the latest commit and displaying the commit hash and message
def cmd_log():
    commit_hash = get_HEAD()
    if not commit_hash:
        print("No commit yet")
        return

    while commit_hash:
        commit = parse_commit(commit_hash)
        print(f"commit {commit_hash}")
        print(f"    {commit['message']}")
        print()
        commit_hash = commit["parent"]

#main function to handle command-line arguments and execute the corresponding commands (init, add, commit, log)
def main():
    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "init":
        cmd_init()
    elif command == "add":
        cmd_add(args[0])
    elif command == "commit":
        message = args[args.index("-m")+1]
        cmd_commit(message)
    elif command == "log":
        cmd_log()
    else:
        print(f"Unkown command: {command}")

if __name__ == "__main__":
    main()
// Reads every file out of a drag-and-drop payload, recursing into folders when the browser
// exposes the (non-standard but widely supported) FileSystemEntry API. Falls back to the
// flat file list on browsers that don't (folder drop degrades to "nothing dropped" there,
// same as the OS just not handing over folder contents).

function readEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject))
}

function fileFromEntry(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject))
}

async function walk(entry: FileSystemEntry, out: File[]): Promise<void> {
  if (entry.isFile) {
    out.push(await fileFromEntry(entry as FileSystemFileEntry))
    return
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader()
    // readEntries must be called repeatedly until it returns an empty array — a single
    // call is not guaranteed to return every child for a large folder.
    let batch = await readEntries(reader)
    while (batch.length > 0) {
      for (const child of batch) await walk(child, out)
      batch = await readEntries(reader)
    }
  }
}

export async function filesFromDataTransferItems(items: DataTransferItemList): Promise<File[]> {
  const entryItems = Array.from(items)
  const entries = entryItems
    .map((item) => item.webkitGetAsEntry())
    .filter((e): e is FileSystemEntry => e != null)

  if (entries.length === 0) {
    return entryItems.map((item) => item.getAsFile()).filter((f): f is File => f != null)
  }

  const files: File[] = []
  for (const entry of entries) await walk(entry, files)
  return files
}

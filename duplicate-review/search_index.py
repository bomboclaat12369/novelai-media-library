"""Bounded independent copies of one FLANN tree for concurrent read searches.

Clones load the very same saved trees: no new candidate selection parameters,
random tree rebuilds, or comparison-cache version changes are introduced.
"""
from contextlib import contextmanager
from queue import SimpleQueue
from pathlib import Path
from tempfile import TemporaryDirectory
import cv2


class SearchIndexes:
    def __init__(self, descriptors, workers):
        self.descriptors = descriptors
        self.indexes = []
        self.available = SimpleQueue()
        primary = cv2.flann_Index(descriptors, dict(algorithm=1, trees=4))
        self.indexes.append(primary)
        # Limit the additional index storage to a conservative ~1 GiB estimate.
        # Search copies are per 256-image block, never per entire collection.
        copies = min(8, workers, 1 + (1024**3)//max(1, descriptors.nbytes*3))
        if copies > 1:
            try:
                with TemporaryDirectory(prefix='duplicate-search-') as directory:
                    saved = str(Path(directory)/'index.flann')
                    primary.save(saved)
                    for _ in range(copies-1):
                        clone = cv2.flann_Index()
                        try:
                            if not clone.load(descriptors, saved):
                                clone.release()
                                break
                        except Exception:
                            clone.release()
                            raise
                        self.indexes.append(clone)
            except (OSError, cv2.error, MemoryError):
                # Failure to allocate an optimization must not invalidate a scan.
                # Successfully created copies still work, including the primary.
                pass
        for index in self.indexes:
            self.available.put(index)

    @contextmanager
    def acquire(self):
        index = self.available.get()
        try:
            yield index
        finally:
            self.available.put(index)

    def close(self):
        for index in self.indexes:
            index.release()
        self.indexes.clear()
        self.descriptors = None

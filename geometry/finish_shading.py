"""Preserve unrounded creases while smoothing finish bevels and their transitions."""
import bmesh


class FinishShading:
    """Track which original face pairs still meet at an unbeveled crease.

    Bevel faces inherit the contributors of their source edge. At a surviving
    miter, the common contributor cancels out, preserving the original sharp
    corner through the bevel strip without marking its tangent boundaries.
    """

    def __init__(self, bm, smooth):
        self.bm = bm
        self.smooth = smooth
        self.layer = bm.faces.layers.int.new('finish_source')
        self.sources = [frozenset()]
        self.source_ids = {frozenset(): 0}
        self.creases = set()
        bm.normal_update()
        for index, face in enumerate(bm.faces):
            face[self.layer] = self._source_id(frozenset((index,)))
        for edge in bm.edges:
            if len(edge.link_faces) == 2 and edge.calc_face_angle(0.0) > .0001:
                first, second = (self.sources[face[self.layer]] for face in edge.link_faces)
                self.creases.update(tuple(sorted((a, b))) for a in first for b in second if a != b)

    def _source_id(self, source):
        if source not in self.source_ids:
            self.source_ids[source] = len(self.sources)
            self.sources.append(source)
        return self.source_ids[source]

    def bevel(self, edges, **options):
        candidates = []
        for edge in edges:
            first, second = (self.sources[face[self.layer]] for face in edge.link_faces)
            self.creases.difference_update(tuple(sorted((a, b))) for a in first for b in second if a != b)
            start, end = (vertex.co.copy() for vertex in edge.verts)
            candidates.append((start, end, first | second))
        result = bmesh.ops.bevel(self.bm, geom=edges, affect='EDGES', mark_sharp=False, **options)
        for face in result['faces']:
            center = face.calc_center_median()
            nearest, distance = frozenset(), float('inf')
            for start, end, source in candidates:
                delta = end - start
                factor = max(0.0, min(1.0, (center - start).dot(delta) / delta.length_squared))
                candidate_distance = (center - start - factor * delta).length_squared
                if candidate_distance < distance:
                    nearest, distance = source, candidate_distance
            face[self.layer] = self._source_id(nearest)
        return result

    def apply(self):
        self.bm.normal_update()
        for face in self.bm.faces:
            face.smooth = self.smooth
        for edge in self.bm.edges:
            if not self.smooth or len(edge.link_faces) != 2:
                edge.smooth = False
                continue
            if edge.calc_face_angle(0.0) <= .0001:
                edge.smooth = True
                continue
            first, second = (self.sources[face[self.layer]] for face in edge.link_faces)
            edge.smooth = not any(tuple(sorted((a, b))) in self.creases
                                  for a in first - second for b in second - first)

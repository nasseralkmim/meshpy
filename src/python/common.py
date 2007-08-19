class _Table:
    def __init__(self):
        self.Rows = []

    def add_row(self, row):
        self.Rows.append([str(i) for i in row])

    def __str__(self):
        columns = len(self.Rows[0])
        col_widths = [max(len(row[i]) for row in self.Rows)
                      for i in range(columns)]

        lines = [
            " ".join([cell.ljust(col_width)
                      for cell, col_width in zip(row, col_widths)])
            for row in self.Rows]
        return "\n".join(lines)




def _linebreak_list(list, per_line=8):
    result = ""
    while len(list) > per_line:
        result += "\t".join(list[:per_line]) + "\n"
        list = list[per_line:]
    return result + "\t".join(list)
        


class MeshInfoBase:
    def set_points(self, points, point_markers=None):
        if point_markers is not None:
            assert len(point_markers) == len(point_markers)

        self.points.resize(len(points))

        for i, pt in enumerate(points):
            self.points[i] = pt
      
        if point_markers is not None:
            for i, mark in enumerate(point_markers):
                self.point_markers[i] = mark





    def set_holes(self, hole_starts):
        self.holes.resize(len(hole_starts))
        for i, hole in enumerate(hole_starts):
            self.holes[i] = hole




    def write_neu(self, outfile, bc={}, periodicity=None, description="MeshPy Output"):
        """Write the mesh out in (an approximation to) Gambit neutral mesh format.
        
        outfile is a file-like object opened for writing.

        bc is a dictionary mapping face markers to a tuple
        (bc_name, bc_code).

        periodicity is either a tuple (face_marker, (px,py,..)) giving the 
        face marker of the periodic boundary and the period in each coordinate
        direction (0 if none) or the value None for no periodicity.
        """

        from meshpy import version
        from datetime import datetime

        # header --------------------------------------------------------------
        outfile.write("CONTROL INFO 2.1.2\n")
        outfile.write("** GAMBIT NEUTRAL FILE\n")
        outfile.write("%s\n" % description)
        outfile.write("PROGRAM: MeshPy VERSION: %s\n" % version)
        outfile.write("%s\n" % datetime.now().ctime())
        
        bc_markers = bc.keys()
        if periodicity:
            periodic_marker, periods = periodicity
            bc_markers.append(periodic_marker)
            
        assert len(self.points)

        dim = len(self.points[0])
        data = (
                ("NUMNP", len(self.points)),
                ("NELEM", len(self.elements)),
                ("NGRPS", 1),
                ("NBSETS", len(bc_markers)),
                ("NDFCD", dim),
                ("NDFVL", dim),
                )

        tbl = _Table()
        tbl.add_row(key for key, value in data)
        tbl.add_row(value for key, value in data)
        outfile.write(str(tbl))
        outfile.write("\n")
        outfile.write("ENDOFSECTION\n")

        # nodes ---------------------------------------------------------------
        outfile.write("NODAL COORDINATES 2.1.2\n")
        for i, pt in enumerate(self.points):
            outfile.write("%d\t%s\n" % 
                    (i+1, "\t".join(repr(c) for c in pt)))
        outfile.write("ENDOFSECTION\n")

        # elements ------------------------------------------------------------
        outfile.write("ELEMENTS/CELLS 2.1.2\n")
        if dim == 2:
            eltype = 3
        else:
            eltype = 6
        for i, el in enumerate(self.elements):
            outfile.write("%d\t%d\t%d\t%s\n" % 
                    (i+1, eltype, len(el), 
                        "\t".join(str(p+1) for p in el)))
        outfile.write("ENDOFSECTION\n")

        # element groups ------------------------------------------------------
        outfile.write("ELEMENT GROUP 1.3.0\n")
        # FIXME
        i = 0
        grp_elements = range(len(self.elements))
        material = 1.
        flags = 0
        outfile.write("GROUP: %d ELEMENTS: %d MATERIAL: %s NFLAGS: %d\n"
                % (1, len(grp_elements), repr(material), flags))
        outfile.write("epsilon: %s\n" % material) # FIXME
        outfile.write("0\n")
        outfile.write(_linebreak_list([str(i+1) for i in grp_elements])
                + "\n")
        outfile.write("ENDOFSECTION\n")

        # boundary conditions -------------------------------------------------
        # build mapping face -> (tet, neu_face_index)
        face2el = {}

        if dim == 2:
            for ti, el in enumerate(self.elements):
                # Sledge++ Users' Guide, figure 4
                faces = [
                        frozenset([el[0], el[1]]),
                        frozenset([el[1], el[2]]),
                        frozenset([el[2], el[0]]),
                        ]
                for fi, face in enumerate(faces):
                    face2el.setdefault(face, []).append((ti, fi+1))

        elif dim == 3:
            face2el = {}
            for ti, el in enumerate(self.elements):
                # Sledge++ Users' Guide, figure 5
                faces = [
                        frozenset([el[1], el[0], el[2]]),
                        frozenset([el[0], el[1], el[3]]),
                        frozenset([el[1], el[2], el[3]]),
                        frozenset([el[2], el[0], el[3]]),
                        ]
                for fi, face in enumerate(faces):
                    face2el.setdefault(face, []).append((ti, fi+1))

        else:
            raise ValueError, "invalid number of dimensions (%d)" % dim

        # actually output bc sections
        assert self.faces.allocated # requires -f option in tetgen

        for bc_marker in bc_markers:
            face_indices = [i
                    for i, face in enumerate(self.faces)
                    if bc_marker == self.face_markers[i]]

            outfile.write("BOUNDARY CONDITIONS 2.1.2\n")
            if bc_marker in bc:
                # regular BC

                bc_name, bc_code = bc[bc_marker]
                outfile.write("%s\t%d\t%d\t%d\t%d\n" 
                        % (bc_name, 
                            1, # face BC
                            len(face_indices),
                            0, # zero additional values per face,
                            bc_code,
                            )
                        )
            else:
                # periodic BC

                outfile.write("periodic\t%s\t%d\t%d\t%d\n"
                        % ("\t".join(repr(p) for p in periods),
                            len(face_indices),
                            0, # zero additional values per face,
                            0,
                            )
                        )

            for i, fi in enumerate(face_indices):
                face_nodes = frozenset(self.faces[fi])
                adj_el = face2el[face_nodes]
                assert len(adj_el) == 1

                el_index, el_face_number = adj_el[0]

                outfile.write("%d\t%d\t%d\n" % 
                        (el_index+1, eltype, el_face_number))

            outfile.write("ENDOFSECTION\n")

        outfile.close()
        # FIXME curved boundaries?
        # FIXME proper element group support





def dump_array(name, array):
    print "array %s: %d elements, %d values per element" % (name, len(array), array.unit)

    if len(array) == 0 or array.unit == 0:
        return

    try:
        array[0]
    except RuntimeError:
        print "  not allocated"
        return

    for i, entry in enumerate(array):
        if isinstance(entry, list):
            print "  %d: %s" % (i, ",".join(str(sub) for sub in entry))
        else:
            print "  %d: %s" % (i, entry)

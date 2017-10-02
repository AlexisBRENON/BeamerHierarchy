#! /usr/bin/env python3
"""
Generate a dot graph representing beamer colors inheritance
"""

import hashlib
import colorsys
import subprocess

from matplotlib import colors

class Node:
    """ A base graphviz node """
    TEMPLATE = ""
    def __init__(self, name):
        self.name = name
        self.id = hashlib.md5(self.name.encode()).hexdigest()
        self.parents = dict(
            both=[],
            fg=[],
            bg=[])

    def __str__(self):
        return self.TEMPLATE.format(self=self)

class Color(Node):
    """ Base class for color nodes """

    @classmethod
    def invert_color(cls, color):
        """ Compute the inverse of a given color """
        rgba = colors.ColorConverter().to_rgba(color)
        inverted = list(rgba)
        for i, channel in enumerate(rgba):
            inverted[i] = ((255 - int(255 * channel)) % 256)/255
        return colors.to_hex(inverted)

    @classmethod
    def _blend(cls, *color_specs):
        """ Blend different colors """
        if len(color_specs) == 1:
            if isinstance(color_specs[0], list):
                return cls._blend(color_specs[0])
            return color_specs[0][0].get(color_specs[0][1])

        result_color = [0, 0, 0]
        for color in color_specs:
            new_rgb = colors.ColorConverter().to_rgb(color[0].get(color[1]))
            for i, channel in enumerate(new_rgb):
                result_color[i] = result_color[i] + (channel * float(color[2]) / 100.)
        result_color.append(
            colors.ColorConverter().to_rgba(color_specs[0][0].get(color_specs[0][1]))[3]
        )
        return colors.to_hex(result_color, True)

    def get(self, color):
        """ Return a color compenent of the Color. """
        raise NotImplementedError()



class RawColor(Color):
    """ A raw color node.

    Raw color are not defined by fg and bg color, just by one unique color.
    """
    TEMPLATE = r"""
"{self.id}":color [label=<<font color="{self.fontcolor}">{self.name}</font>> fillcolor="{self.color}" fontcolor="{self.fontcolor}" rank="source"]
"""
    def __init__(self, name):
        super().__init__(name)
        self.color = "#FFFFFFFF"
        self.fontcolor = "#000000FF"

    def set_color(self, color):
        """ Set the raw color.

        Returns:
            self
        """
        self.color = colors.to_hex(color, True)
        self.fontcolor = self.invert_color(self.color)
        return self

    def get(self, _):
        return self.color

class BeamerColor(Color):
    """ A beamer color, defined by its fg and bg color.

    It is also linked to parents from which it inherits its colors.
    """
    TEMPLATE = """
"{self.id}" [shape="none" label=<
    <table border="0" cellborder="1" cellspacing="0"
    ><tr>
        <td bgcolor="{self.bg}" PORT="bgin">
            <font color="{self.inverted_bg}">bg:{self.bg}</font>
        </td>
        <td bgcolor="{self.fg}" PORT="fgin">
            <font color="{self.inverted_fg}">fg:{self.fg}</font>
        </td>
    </tr><tr>    
        <td colspan="2" bgcolor="{self.bg}">
            <font color="{self.fg}">
            <br/>
            {self.name}
            <br/>
            </font>
        </td>
    </tr><tr>
        <td bgcolor="{self.bg}" PORT="bgout">
            <font color="{self.inverted_bg}">bg:{self.bg}</font>
        </td>
        <td bgcolor="{self.fg}" PORT="fgout">
            <font color="{self.inverted_fg}">fg:{self.fg}</font>
        </td>
    </tr></table>>]
"""
    def __init__(self, name):
        super().__init__(name)
        self.fg = "#FFFFFF00"
        self.inverted_fg = "#000000FF"
        self.bg = "#00000000"
        self.inverted_bg = "#000000FF"

    def set_parent(self, parent):
        """ Set the parent of the color.
        This colors is strictly equivalent to its parent.

        Returns: self
        """
        self.parents["both"].append(parent.id)
        self._set_fg(parent.fg)
        self._set_bg(parent.bg)
        return self

    def _set_fg(self, _fg):
        self.fg = colors.to_hex(_fg, True)
        self.inverted_fg = self.invert_color(self.fg)
        return self

    def _set_bg(self, _bg):
        self.bg = colors.to_hex(_bg, True)
        self.inverted_bg = self.invert_color(self.bg)
        return self

    def inherit(self, ground_to, *color_specs):
        """ Add an inheritance relation between self.ground_to and color.ground_from.

        args:
            ground_to (str): which part of self to define
            color_specs: multiples tuples of type (color, ground, percent) used to blend
        returns: self
        """

        color_to_apply = self._blend(*color_specs)
        for color_spec in color_specs:
            if color_spec[1] in ["fg", "bg"]:
                ground_from = color_spec[1] + "out"
            else:
                ground_from = "color"
            self.parents[ground_to].append('"%s":%s' % (color_spec[0].id, ground_from))

        if ground_to == "fg":
            self._set_fg(color_to_apply)
        elif ground_to == "bg":
            self._set_bg(color_to_apply)
        return self

    def get(self, color):
        if color == "fg":
            return self.fg
        if color == "bg":
            return self.bg
        raise RuntimeError()

    def __str__(self):
        result = super().__str__()
        for port_from in self.parents["both"]:
            result += '"{}":s -> "{}":n [style=dotted]\n'.format(port_from, self.id)
        for port_to, head in [("fg", "obox"), ("bg", "box")]:
            for port_from in self.parents[port_to]:
                tail = "none"
                if ":fg" in port_from:
                    tail = "oinv"
                elif ":bg" in port_from:
                    tail = "inv"
                result += '{}:s -> "{}":{}in:n [dir=both,arrowtail={},arrowhead={}]\n'.format(
                    port_from,
                    self.id,
                    port_to,
                    tail,
                    head,
                    )
        return result

class BeamerColorGraph:
    """ Base graph """
    TEMPLATE = """
    strict digraph "{self.id}" {{
        graph [truecolor=true, bgcolor="#FFFFFF00", label="{self.name}", concentrate=true, sep=0.5]
        node [style=filled, color="black", fillcolor="#FFFFFF00"]
        {stmt}
    }}
    """
    def __init__(self, name):
        self.name = name
        self.id = hashlib.md5(self.name.encode()).hexdigest()
        self.colors = {}

    def add_colors(self, color_nodes):
        """ Add some color nodes to the graph. """
        if isinstance(color_nodes, dict):
            self.colors.update(color_nodes)
        else:
            self.colors.update([(c.name, c) for c in color_nodes])
        return self

    def __str__(self):
        stmt = ""
        for color in self.colors.values():
            stmt += str(color)
        return self.TEMPLATE.format(
            self=self,
            stmt=stmt
            )

    def generate(self):
        """ Actually generate the graph. """
        try:
            subprocess.run(
                [
                    "dot",
                    "-T", "svg",
                    "-o", "%s.svg" % self.name.translate(str.maketrans(" /:", "_-_"))
                ],
                input=str(self).encode(),
                check=True
                )
        except subprocess.CalledProcessError as error:
            print(self)
            print(error.stdout)
            print(error.stderr)

class BeamerColorSubgraph(BeamerColorGraph):
    """ Graphviz subgraph """
    TEMPLATE = """
    subgraph "{self.id}" {{
        graph [label="{self.name}"]
        {stmt}
    }}
    """

class _Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(_Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class BeamerColorDefault(BeamerColorGraph, metaclass=_Singleton):
    def __init__(self):
        super().__init__("Beamer color theme : default")
        nodes = {}

        base_colors = {}
        base_colors['black'] = RawColor('black').set_color("black")
        base_colors['white'] = RawColor('white').set_color("white")
        base_colors['red'] = RawColor('red').set_color("red")
        base_colors['green'] = RawColor('green').set_color("green")
        base_colors['beamer@blendedblue'] = RawColor('beamer@blendedblue').set_color(
            (0.2, 0.2, 0.7)
        )
        nodes['base_colors'] = BeamerColorSubgraph('base colors').add_colors(
            base_colors
        )

        nodes['normal text'] = BeamerColor('normal text').inherit(
            "fg", (base_colors['black'], "color")
        ).inherit(
            "bg", (base_colors['white'], "color"))
        nodes['alerted text'] = BeamerColor('alerted text').inherit(
            "fg",
            (base_colors['red'], "color")
        )
        nodes['example text'] = BeamerColor('example text').inherit(
            "fg",
            (base_colors['black'], "color", 50),
            (base_colors['green'], "color", 50)
        )

        nodes['structure'] = BeamerColor('structure').inherit(
            "fg",
            (base_colors['beamer@blendedblue'], "color")
        )

        nodes['background canvas'] = BeamerColor('background canvas').set_parent(
            nodes['normal text']
        )
        nodes['background'] = BeamerColor('background').set_parent(
            nodes['background canvas']
        )

        palette = {}
        palette['primary'] = BeamerColor('palette primary').inherit(
            "fg",
            (nodes['structure'], "fg")
        )
        palette['secondary'] = BeamerColor('palette secondary').inherit(
            "fg",
            (base_colors['black'], "color", 25),
            (nodes['structure'], "fg", 75)
        )
        palette['tertiary'] = BeamerColor('palette tertiary').inherit(
            "fg",
            (base_colors['black'], "color", 50),
            (nodes['structure'], "fg", 50)
        )
        palette['quaternary'] = BeamerColor('palette quaternary').inherit(
            "fg",
            (base_colors['black'], "color")
        )
        nodes['palette'] = BeamerColorSubgraph('palette').add_colors(
            palette
        )


        palette_sidebar = {}
        palette_sidebar['primary'] = BeamerColor('palette sidebar primary').inherit(
            "fg",
            (nodes['normal text'], "fg")
        )
        palette_sidebar['secondary'] = BeamerColor('palette sidebar secondary').inherit(
            "fg",
            (nodes['structure'], "fg")
        )
        palette_sidebar['tertiary'] = BeamerColor('palette sidebar tertiary').inherit(
            "fg",
            (nodes['normal text'], "fg")
        )
        palette_sidebar['quaternary'] = BeamerColor('palette sidebar quaternary').inherit(
            "fg",
            (nodes['structure'], "fg")
        )
        nodes['palette sidebar'] = BeamerColorSubgraph('palette sidebar').add_colors(
            palette_sidebar
        )

        math = {}
        math['text'] = BeamerColor('math text')
        math['text inlined'] = BeamerColor('math text inlined').set_parent(
            math['text']
        )
        math['text displayed'] = BeamerColor('math text displayed').set_parent(
            math['text']
        )
        math['normal'] = BeamerColor('normal text in math mode')
        nodes['math'] = BeamerColorSubgraph('math').add_colors(
            math
        )

        nodes['local structure'] = BeamerColor('local structure').set_parent(
            nodes['structure']
        )

        title = {}
        title['titlelike'] = BeamerColor('titlelike').set_parent(
            nodes['structure']
        )
        title['title'] = BeamerColor('title').set_parent(
            title['titlelike']
        )
        title['head/foot'] = BeamerColor('title in head/foot').set_parent(
            palette['quaternary']
        )
        title['sidebar'] = BeamerColor('title in sidebar').set_parent(
            palette_sidebar['quaternary']
        )
        title['subtitle'] = BeamerColor('subtitle').set_parent(
            title['title']
        )
        title['frametitle'] = BeamerColor('frametitle').set_parent(
            title['titlelike']
        )
        title['framesubtitle'] = BeamerColor('framesubtitle').set_parent(
            title['frametitle']
        )
        title['frametitle right'] = BeamerColor('frametitle right').set_parent(
            title['frametitle']
        )
        nodes['title'] = BeamerColorSubgraph('title').add_colors(
            title
        )

        author = {}
        author['author'] = BeamerColor('author')
        author['head/foot'] = BeamerColor('author in head/foot').set_parent(
            palette['primary']
        )
        author['sidebar'] = BeamerColor('author in sidebar').inherit(
            "fg",
            (palette_sidebar['tertiary'], "fg")
        )
        nodes['author'] = BeamerColorSubgraph('author').add_colors(
            author
        )

        institute = {}
        institute['institute'] = BeamerColor('institute')
        institute['head/foot'] = BeamerColor('institute in head/foot').set_parent(
            palette['tertiary']
        )
        institute['sidebar'] = BeamerColor('institute in sidebar').inherit(
            "fg",
            (palette_sidebar['tertiary'], "fg")
        )
        nodes['institute'] = BeamerColorSubgraph('institute').add_colors(
            institute
        )

        date = {}
        date['date'] = BeamerColor('date')
        date['head/foot'] = BeamerColor('date in head/foot').set_parent(
            palette['secondary']
        )
        date['sidebar'] = BeamerColor('date in sidebar').inherit(
            "fg",
            (palette_sidebar['tertiary'], "fg")
        )
        nodes['date'] = BeamerColorSubgraph('date').add_colors(
            date
        )

        nodes['titlegraphic'] = BeamerColor('titlegraphic')

        part = {}
        part['name'] = BeamerColor('part name')
        part['title'] = BeamerColor('part title').set_parent(
            title['titlelike']
        )
        nodes['part'] = BeamerColorSubgraph('part').add_colors(part)

        section = {}
        section['name'] = BeamerColor('section name')
        section['title'] = BeamerColor('section title').set_parent(
            title['titlelike']
        )
        section['in toc'] = BeamerColor('section in toc').set_parent(
            nodes['structure']
        )
        section['in toc shaded'] = BeamerColor('section in toc shaded').set_parent(
            section['in toc']
        )
        section['in head/foot'] = BeamerColor('section in head/foot').set_parent(
            palette['tertiary']
        )
        section['in sidebar'] = BeamerColor('section in sidebar').set_parent(
            palette_sidebar['secondary']
        )
        section['in sidebar shaded'] = BeamerColor('section in sidebar shaded').inherit(
            "fg",
            (section['in sidebar'], "fg", 40),
            (section['in sidebar'], "bg", 60)
        )
#    TODO: activate it
#    section['number projected'] = BeamerColor('section number projected').set_parent(
#         item['projected']
#    )
        nodes['section'] = BeamerColorSubgraph('section').add_colors(
            section
        )

        subsection = {}
        subsection['name'] = BeamerColor('subsection name')
        subsection['title'] = BeamerColor('subsection title').set_parent(
            title['titlelike']
        )
        subsection['in toc'] = BeamerColor('subsection in toc')
        subsection['in toc shaded'] = BeamerColor('subsection in toc shaded').set_parent(
            subsection['in toc']
        )
        subsection['in head/foot'] = BeamerColor('subsection in head/foot').set_parent(
            palette['secondary']
        )
        subsection['in sidebar'] = BeamerColor('subsection in sidebar').set_parent(
            palette_sidebar['primary']
        )
        subsection['in sidebar shaded'] = BeamerColor('subsection in sidebar shaded').inherit(
            "fg",
            (subsection['in sidebar'], "fg", 40),
            (subsection['in sidebar'], "bg", 60)
        )
#    TODO: activate it
#    subsection['number projected'] = BeamerColor('subsection number projected').set_parent(
#         subitem['projected']
#    )
        nodes['subsection'] = BeamerColorSubgraph('subsection').add_colors(
            subsection
        )

        subsubsection = {}
        subsubsection['in toc'] = BeamerColor('subsubsection in toc').set_parent(
            subsection['in toc']
        )
        subsubsection['in toc shaded'] = BeamerColor('subsubsection in toc shaded').set_parent(
            subsubsection['in toc']
        )
        subsubsection['in head/foot'] = BeamerColor('subsubsection in head/foot').set_parent(
            subsection['in head/foot']
        )
        subsubsection['in sidebar'] = BeamerColor('subsubsection in sidebar').set_parent(
            subsection['in sidebar']
        )
        subsubsection['in sidebar shaded'] = BeamerColor('subsubsection in sidebar shaded').set_parent(
            subsection['in sidebar shaded']
        )
#    TODO: activate it
#    subsubsection['number projected'] = BeamerColor('subsubsection number projected').set_parent(
#         subsubitem['projected']
#    )
        nodes['subsubsection'] = BeamerColorSubgraph('subsubsection').add_colors(
            subsubsection
        )

        nodes['headline'] = BeamerColor('headline')
        nodes['footline'] = BeamerColor('footline')

        sidebar = {}
        sidebar['sidebar'] = BeamerColor('sidebar')
        sidebar['left'] = BeamerColor('sidebar left').set_parent(
            sidebar['sidebar']
        )
        sidebar['right'] = BeamerColor('sidebar right').set_parent(
            sidebar['sidebar'])
        nodes['sidebar'] = BeamerColorSubgraph('sidebar').add_colors(
            sidebar)

        nodes['logo'] = BeamerColor('logo').set_parent(
            palette['secondary'])

        caption = {
            "caption" : BeamerColor('caption'),
            "name" : BeamerColor('caption name').set_parent(
                nodes['structure'])
        }
        nodes['caption'] = BeamerColorSubgraph('caption').add_colors(
            caption)

        navigation = {}
        navigation["button"] = BeamerColor('button').inherit(
            "bg",
            (nodes['local structure'], "fg", 50),
            (nodes['local structure'], "bg", 50)
        ).inherit(
            "fg",
            (base_colors['white'], "colors")
        )
        navigation['button border'] = BeamerColor('button border').inherit(
            "fg",
            (navigation['button'], "bg")
            )
        navigation['symbols'] = BeamerColor('symbols').inherit(
            "fg",
            (nodes['structure'], "fg", 40),
            (nodes['structure'], "bg", 60)
            )
        navigation['symbols dimmed'] = BeamerColor('symbols dimmed').inherit(
            "fg",
            (nodes['structure'], "fg", 20),
            (nodes['structure'], "bg", 80)
            )
        navigation['mini frame'] = BeamerColor('mini frame').set_parent(
            section['in head/foot'])
        nodes['navigation'] = BeamerColorSubgraph('navigation').add_colors(
            navigation)

        block = {}
        block['body'] = BeamerColor('block body')
        block['body alerted'] = BeamerColor('block body alerted')
        block['body example'] = BeamerColor('block body example')
        block['title'] = BeamerColor('block title').set_parent(
            nodes['structure'])
        block['title alerted'] = BeamerColor('block title alerted').set_parent(
            nodes['alerted text'])
        block['title example'] = BeamerColor('block title example').set_parent(
            nodes['example text'])
        nodes['block'] = BeamerColorSubgraph('block').add_colors(
            block)

        item = {}
        item['item'] = BeamerColor('item').set_parent(
            nodes['local structure'])
        item['projected'] = BeamerColor('item projected').set_parent(
            nodes['local structure']
        ).inherit(
            "fg",
            (base_colors['white'], "color")
        ).inherit(
            "bg",
            (item['item'], "fg")
        )
        item['enumerate'] = BeamerColor('enumerate item').set_parent(
            item['item'])
        item['itemize'] = BeamerColor('itemize item').set_parent(
            item['item'])
        item['body'] = BeamerColor('itemize/enumerate body')
        item['description'] = BeamerColor('description item').set_parent(
            item['item'])
        item['description body'] = BeamerColor('description body')
        item['bibliography'] = BeamerColor('bibliography item').set_parent(
            item['item'])
        nodes['item'] = BeamerColorSubgraph('item').add_colors(
            item)

        subitem = {}
        subitem['subitem'] = BeamerColor('subitem').set_parent(
            item['item'])
        subitem['projected'] = BeamerColor('subitem projected').set_parent(
            item['projected']
        )
        subitem['enumerate'] = BeamerColor('enumerate subitem').set_parent(
            subitem['subitem'])
        subitem['itemize'] = BeamerColor('itemize subitem').set_parent(
            subitem['subitem'])
        subitem['body'] = BeamerColor('itemize/enumerate subbody')
        nodes['subitem'] = BeamerColorSubgraph('subitem').add_colors(
            subitem)

        subsubitem = {}
        subsubitem['subsubitem'] = BeamerColor('subsubitem').set_parent(
            subitem['subitem'])
        subsubitem['projected'] = BeamerColor('subsubitem projected').set_parent(
            subitem['projected']
        )
        subsubitem['enumerate'] = BeamerColor('enumerate subsubitem').set_parent(
            subsubitem['subsubitem'])
        subsubitem['itemize'] = BeamerColor('itemize subsubitem').set_parent(
            subsubitem['subsubitem'])
        subsubitem['body'] = BeamerColor('itemize/enumerate subsubbody')
        nodes['subsubitem'] = BeamerColorSubgraph('subsubitem').add_colors(
            subsubitem)

        bibliography = {}
        bibliography['author'] = BeamerColor('bibliography entry author').inherit(
            "fg",
            (nodes['structure'], "fg")
        )
        bibliography['title'] = BeamerColor('bibliography entry title').inherit(
            "fg",
            (nodes['normal text'], "fg")
        )
        bibliography['location'] = BeamerColor('bibliography entry location').inherit(
            "fg",
            (nodes['structure'], "fg", 65),
            (nodes['structure'], "bg", 35)
        )
        bibliography['note'] = BeamerColor('bibliography entry note').inherit(
            "fg",
            (nodes['structure'], "fg", 65),
            (nodes['structure'], "bg", 35)
        )
        nodes['bibliography'] = BeamerColorSubgraph('bibliography').add_colors(
            bibliography)

        separation_line = {}
        separation_line['separation line'] = BeamerColor('separation line')
        separation_line['upper head'] = BeamerColor('upper separation line head').set_parent(
            separation_line['separation line']
            )
        separation_line['middle head'] = BeamerColor('middle separation line head').set_parent(
            separation_line['separation line']
            )
        separation_line['lower head'] = BeamerColor('lower separation line head').set_parent(
            separation_line['separation line']
            )
        separation_line['upper foot'] = BeamerColor('upper separation line foot').set_parent(
            separation_line['separation line']
            )
        separation_line['middle foot'] = BeamerColor('middle separation line foot').set_parent(
            separation_line['separation line']
            )
        separation_line['lower foot'] = BeamerColor('lower separation line foot').set_parent(
            separation_line['separation line']
            )
        nodes['separation line'] = BeamerColorSubgraph('separation line').add_colors(
            separation_line)

        abstract = {
            "abstract" : BeamerColor('abstract'),
            "title" : BeamerColor('abstract title').set_parent(
                nodes['structure'])
            }
        nodes['abstract'] = BeamerColorSubgraph('abstract').add_colors(
            abstract)

        nodes['verse'] = BeamerColor('verse')

        quote = {}
        quote['quotation'] = BeamerColor('quotation')
        quote['quote'] = BeamerColor('quote').set_parent(
            quote['quotation'])

        nodes['page number'] = BeamerColor('page number in head/foot')

        nodes['qed symbol'] = BeamerColor('qed symbol').set_parent(
            nodes['structure'])

        note = {}
        note['page'] = BeamerColor('note page').inherit(
            "bg",
            (base_colors['white'], "color", 90),
            (base_colors['black'], "color", 10)
        ).inherit(
            "fg",
            (base_colors['black'], "color")
        )
        note['title'] = BeamerColor('note title').inherit(
            "bg",
            (base_colors['white'], "color", 80),
            (base_colors['black'], "color", 20)
        ).inherit(
            "fg",
            (base_colors['black'], "color")
        )
        note['date'] = BeamerColor('note date').set_parent(
            note['title']
        )
        nodes['note'] = BeamerColorSubgraph('note').add_colors(
            note)

        self.add_colors(nodes)

if __name__ == "__main__":
    BeamerColorDefault().generate()


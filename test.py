import urwid

def create_canvas():
    # Create a canvas using urwid.Canvas
    width = 40
    height = 20
    
    # Unicode characters - encode them to bytes
    block = '█'.encode('utf-8')
    arrow = '↟'.encode('utf-8')
    vline = '='.encode('utf-8')
    
    # Create canvas content as a list of rows
    content = []
    for y in range(height):
        row = []
        for x in range(width):
            # Place arrow in center
            if y == height // 2 and x == width // 2:
                row.append((('arrow',), arrow))
            # Place vertical lines every other column
            elif x % 2 == 0:
                row.append((('vline',), vline))
            else:
                row.append((('block',), block))
        content.append(row)
    
    # Create the canvas
    canvas = urwid.TextCanvas(content, encoding='utf-8')
    return canvas

def main():
    # Define color palette
    palette = [
        ('block', 'light blue', 'light blue'),
        ('arrow', 'white', 'light blue'),
        ('line', 'white', 'black'),
        ('vline', 'white', 'dark green'),
    ]
    
    # Create the canvas
    canvas = create_canvas()
    
    # Create a BoxWidget that renders our canvas
    class CanvasWidget(urwid.BoxWidget):
        def __init__(self, canvas):
            self.canvas = canvas
        
        def render(self, size, focus=False):
            return self.canvas
        
        def rows(self, size, focus=False):
            return 20
        
        def cols(self, size, focus=False):
            return 40
    
    canvas_widget = CanvasWidget(canvas)
    
    # Put the canvas in a LineBox
    lined_canvas = urwid.LineBox(canvas_widget)
    
    # Create main widget structure
    main_widget = urwid.Padding(lined_canvas, align='center', width=('relative', 95))
    main_widget = urwid.Filler(main_widget, valign='middle', height=('relative', 95))
    
    # Create and run the main loop
    loop = urwid.MainLoop(main_widget, palette)
    loop.run()

if __name__ == '__main__':
    main()

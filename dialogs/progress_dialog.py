import urwid

class ProgressDialog(urwid.WidgetWrap):
    def __init__(self, message="Loading..."):
        self.position = 0
        self.message = message
        self.throbber_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        
        # Create separate widgets for throbber and message
        self.throbber = urwid.Text('', align='center')
        self.text = urwid.Text(message, align='center')
        self._update_text()
        
        # Create the layout with throbber and message on separate lines
        pile = urwid.Pile([
            urwid.Text(''),  # Top spacing
            self.throbber,   # Throbber on its own line
            self.text,       # Message below throbber
            urwid.Text(''),  # Bottom spacing
        ])
        
        # Create a LineBox with padding
        box = urwid.LineBox(
            urwid.Padding(urwid.Filler(pile), left=2, right=2),
            title="Please Wait"
        )
        
        self._w = urwid.AttrMap(box, 'dialog')
        
        # Start the animation
        self.animate_alarm = None
    
    def _update_text(self):
        """Update the throbber"""
        throbber = self.throbber_chars[self.position]
        self.throbber.set_text(throbber)
    
    def start_animation(self, loop):
        """Start the throbber animation"""
        self.animate_alarm = loop.set_alarm_in(0.1, self._animate)
    
    def _animate(self, loop, user_data):
        """Animate the throbber"""
        self.position = (self.position + 1) % len(self.throbber_chars)
        self._update_text()
        self.animate_alarm = loop.set_alarm_in(0.1, self._animate)
    
    def stop_animation(self, loop):
        """Stop the throbber animation"""
        if self.animate_alarm:
            loop.remove_alarm(self.animate_alarm) 
import urwid

class ErrorDialog(urwid.WidgetWrap):
    def __init__(self, error_msg, app, retry_callback=None):
        self.app = app
        self.retry_callback = retry_callback
        
        # Create buttons
        retry_btn = urwid.Button("Retry", on_press=self._on_retry)
        close_btn = urwid.Button("Exit", on_press=self._on_close)
        retry_btn = urwid.AttrMap(retry_btn, 'button', focus_map='button_focus')
        close_btn = urwid.AttrMap(close_btn, 'button', focus_map='highlight_red')
        
        buttons = urwid.GridFlow([retry_btn, close_btn], 12, 3, 1, 'center')
        
        # Create error message
        pile = urwid.Pile([
            urwid.Text(''),
            urwid.Text(error_msg, align='center'),
            urwid.Text(''),
            buttons,
            urwid.Text('')
        ])
        
        fill = urwid.Filler(pile, 'middle')
        box = urwid.LineBox(
            urwid.Padding(fill, left=2, right=2),
            title="Error"
        )
        self._w = urwid.AttrMap(box, 'error_dialog')
    
    def _on_retry(self, button):
        if self.retry_callback:
            self.retry_callback()
        # Remove dialog and return to main view
        self.app.loop.widget = self.app.frame
    
    def _on_close(self, button):
        raise urwid.ExitMainLoop() 
"""`python -m unboringspec`: the same CLI without the `unboring` launcher.

On Windows the launcher is a small .exe in the environment's Scripts folder, and antivirus or company
policies can block it; running the package through Python avoids that.
"""

from .cli import app

app(prog_name="unboring")

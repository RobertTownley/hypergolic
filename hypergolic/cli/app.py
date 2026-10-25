import typer
from rich.console import Console

from hypergolic.cli.doctor_cmd import doctor
from hypergolic.cli.init_cmd import init
from hypergolic.cli.run_cmd import run as run_cmd
from hypergolic.cli.update_cmd import update as update_cmd
from hypergolic.cli.version import get_version

app = typer.Typer(
    name="hypergolic",
    help="Hypergolic — AI-powered coding assistant.",
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"hypergolic [bold cyan]{get_version()}[/]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    pass


app.command()(init)
app.command(name="run")(run_cmd)
app.command(name="update")(update_cmd)
app.command()(doctor)

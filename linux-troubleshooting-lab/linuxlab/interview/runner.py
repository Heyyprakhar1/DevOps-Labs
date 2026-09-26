import random
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from linuxlab.interview.questions import INTERVIEW_SCENARIOS
from linuxlab.ai.ollama import OllamaClient

console = Console()

class InterviewRunner:
    """Runs interactive scenario-based troubleshooting interviews."""

    def __init__(self):
        self.ai = OllamaClient()

    def run(self):
        scenario = random.choice(INTERVIEW_SCENARIOS)

        console.print()
        console.print(Panel(
            f"[bold yellow]TOPIC:[/bold yellow] {scenario['topic']}\n\n{scenario['initial_prompt']}",
            title="[bold cyan]LINUX SRE TROUBLESHOOTING INTERVIEW[/bold cyan]",
            border_style="cyan"
        ))

        try:
            # First answer
            ans1 = Prompt.ask("\n[bold green]Your Diagnostic Hypothesis[/bold green]")

            # Follow-up questions
            follow_answers = []
            for i, fq in enumerate(scenario["follow_ups"], 1):
                console.print(f"\n[bold yellow]Interviewer Follow-up #{i}:[/bold yellow] {fq}")
                f_ans = Prompt.ask("[bold green]Your Answer[/bold green]")
                follow_answers.append((fq, f_ans))
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Interview session ended by user.[/yellow]")
            return

        # Check for optional Ollama AI evaluation
        ai_evaluation = None
        if self.ai.is_available() and ans1.strip():
            console.print("\n[dim]Consulting Senior SRE AI evaluator...[/dim]")
            transcript = f"Question: {scenario['initial_prompt']}\nCandidate Answer: {ans1}\n"
            for q, a in follow_answers:
                transcript += f"Follow-up: {q}\nAnswer: {a}\n"
            prompt = (
                f"{transcript}\n"
                "Evaluate the candidate's answers as a Senior Staff SRE interviewer. "
                "Highlight: 1. Strong reasoning points. 2. Misconceptions or gaps. 3. Final rating (Hire/No Hire for 2 YOE SRE)."
            )
            ai_evaluation = self.ai.generate(prompt, system="You are an expert SRE interview evaluator.")

        console.print()
        if ai_evaluation:
            console.print(Panel(
                ai_evaluation,
                title="[bold magenta]AI INTERVIEW EVALUATION[/bold magenta]",
                border_style="magenta"
            ))

        console.print(Panel(
            scenario["sre_breakdown"],
            title="[bold green]STAFF SRE BENCHMARK BREAKDOWN[/bold green]",
            border_style="green"
        ))

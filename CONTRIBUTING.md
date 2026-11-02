# Contributing

Thank you for your interest in contributing to this project! Contributions, suggestions, bug reports, and improvements are welcome.

Please follow the guidelines below to help keep contributions clear, consistent, and easy to review.

## Getting Started

1. Read the repository's `README.md` to understand the project's purpose, features, and setup instructions.
2. Check the existing issues and pull requests to see whether the problem or idea has already been discussed.
3. If you are planning a major change, open an issue first so the proposed approach can be discussed.
4. Fork the repository and clone your fork to your local machine.

```bash
git clone https://github.com/<your-username>/<repository-name>.git
cd <repository-name>
```

Add the original repository as the upstream remote when working from a fork:

```bash
git remote add upstream https://github.com/joshuaarao42-arch/<repository-name>.git
```

## Making Changes

- Create a separate branch for each feature, fix, or documentation update.
- Use a clear, descriptive branch name, such as `feature/add-search`, `fix/login-validation`, or `docs/update-readme`.
- Keep changes focused. Avoid unrelated edits in the same pull request.
- Follow the conventions and structure already used in the project.
- Write clear comments only when they help explain code that may not be obvious.
- Update the README or other documentation when your changes affect setup, usage, or project behavior.
- Do not commit passwords, API keys, access tokens, private data, or other secrets.

## Code Quality

Before submitting your changes:

- Check your code for errors and remove unused code or debugging statements.
- Run the project using the instructions in its README.
- Run any existing tests, checks, or linters that apply to the project.
- Verify that existing features still work and that your changes behave as expected.
- Keep formatting and naming consistent with the existing codebase.

If the project does not have automated tests, include the manual testing steps you performed in your pull request.

## Commit Messages

Use short, descriptive commit messages. A simple format is:

```text
type: short description
```

Suggested types:

- `feat`: add a feature
- `fix`: fix a bug
- `docs`: update documentation
- `style`: formatting or code-style changes
- `refactor`: improve code without changing its behavior
- `test`: add or update tests
- `chore`: maintenance tasks

Examples:

```text
feat: add task filtering
fix: handle empty form input
docs: improve installation instructions
```

## Submitting a Pull Request

1. Push your branch to your fork.
2. Open a pull request against the original repository's default branch.
3. Give the pull request a clear title.
4. Describe what changed and why.
5. Link any related issue.
6. Include screenshots or sample output when changes affect the user interface or visible behavior.
7. Mention the tests or manual checks you completed.

A pull request should be focused, understandable, and ready for review. Be open to feedback and make requested changes when appropriate.

## Reporting Bugs or Suggesting Features

When opening an issue, please provide enough information for the project maintainer to understand the request.

For bug reports, include:

- A clear and descriptive title.
- Steps to reproduce the problem.
- Expected behavior and actual behavior.
- Relevant error messages, logs, or screenshots.
- Your operating system and relevant runtime or tool versions, when applicable.

For feature requests, explain the problem the feature would solve, how it could work, and any useful examples.

## Questions and Discussions

For questions or ideas, open an issue in the relevant repository and provide the necessary context. Please keep discussions respectful and focused on improving the project.

## Code of Conduct

Be respectful, constructive, and considerate when interacting with other contributors. Harassment, discrimination, personal attacks, and disrespectful behavior are not acceptable.

By participating in this project, you agree to help maintain a welcoming and collaborative environment.

---

Thank you for helping improve this project!

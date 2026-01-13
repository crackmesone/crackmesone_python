# Contributing to crackmes.one

Thank you for your interest in contributing to crackmes.one!

## Ways to Contribute

- **Report bugs** - Found something broken? Open an [issue](https://github.com/crackmesone/crackmesone_python/issues)
- **Suggest features** - Have an idea? Open an issue to discuss it
- **Submit pull requests** - Fix bugs or implement new features

## Before You Start

**Important:** If you're planning to contribute code, you **must** contact the project maintainer first via [Discord](https://discord.gg/2pPV3yq) or email (crackmesone@gmail.com) before starting any work. This applies to all contributions, whether or not they're tracked by an existing issue.

**Pull requests submitted without prior communication may be rejected without consideration.**

This requirement helps us:

- Avoid duplicate work
- Discuss the best approach
- Ensure your contribution aligns with the project direction

## Development Setup

```bash
# Clone the repository
git clone https://github.com/crackmesone/crackmesone_python.git
cd crackmesone_python

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy config template and configure
cp config/config.json.example config/config.json
# Edit config/config.json with your settings

# Run the development server
python run.py
```

## Reporting Issues

When reporting issues, please include:

- Steps to reproduce the problem
- Expected behavior vs actual behavior
- Browser/OS information if relevant
- Screenshots if applicable

## Questions?

Feel free to reach out via:
- Discord: https://discord.gg/2pPV3yq
- Email: crackmesone@gmail.com

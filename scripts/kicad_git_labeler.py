#!/usr/bin/env python3
"""
KiCad Project Git Auto-labeler
Automatically updates version text variables in KiCad projects based on git info
Supports both JSON (KiCad 9+) and S-expression (KiCad 6-8) formats
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_git_info(repo_dir):
    """Get git revision and date information."""
    try:
        # Get the most recent tag
        try:
            last_tag = subprocess.check_output(
                ['git', 'describe', '--tags', '--abbrev=0'],
                cwd=repo_dir,
                stderr=subprocess.DEVNULL
            ).decode().strip()
        except subprocess.CalledProcessError:
            # No tags found, use v0.0.0 as baseline
            last_tag = 'v0.0.0'
        
        # Get number of commits since the last tag
        commits_since_tag = subprocess.check_output(
            ['git', 'rev-list', f'{last_tag}..HEAD', '--count'],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        # Get current branch name
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        # Build revision string
        if commits_since_tag == '0':
            # We're exactly on a tag
            revision = last_tag
        else:
            # We have commits after the tag
            revision = f"{last_tag}.{commits_since_tag}"
        
        # Get the commit date
        commit_date = subprocess.check_output(
            ['git', 'log', '-1', '--format=%ci'],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        if not commit_date:
            commit_date = datetime.now().strftime('%Y-%m-%d')
        else:
            commit_date = commit_date.split()[0]
        
        # Check if there are uncommitted changes
        if subprocess.check_output(
            ['git', 'status', '--porcelain'],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL
        ).decode().strip():
            status= 'dirty'
        else:
            status = 'clean'
        
        return revision, status, commit_date, branch
        
    except subprocess.CalledProcessError as e:
        print(f"Error: Not in a git repository or git command failed", file=sys.stderr)
        return None, None, None


def update_kicad_project_json(project_file, dry_run=False):
    """Update text variables in JSON format KiCad project file (KiCad 9+)."""
    
    repo_dir = project_file.parent
    
    # Get git information
    revision, status, date, branch = get_git_info(repo_dir)
    if revision is None:
        return False
    
    # Read and parse JSON
    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: {project_file} is not valid JSON: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error reading {project_file}: {e}", file=sys.stderr)
        return False
    
    # Ensure text_variables exists
    if 'text_variables' not in data:
        data['text_variables'] = {}
    
    # Check if values changed
    changed = False
    if data['text_variables'].get('VERSION') != revision:
        changed = True
    if data['text_variables'].get('BUILD_DATE') != date:
        changed = True
    if data['text_variables'].get('STATUS') != status:
        changed = True
    if data['text_variables'].get('BRANCH') != branch:
        changed = True
    
    # Update the variables
    data['text_variables']['VERSION'] = revision
    data['text_variables']['BUILD_DATE'] = date
    data['text_variables']['STATUS'] = status
    data['text_variables']['BRANCH'] = branch
    
    if not changed:
        print(f"No changes needed for {project_file}")
        return True
    
    if dry_run:
        print(f"Would update {project_file}:")
        print(f"  VERSION: {revision}")
        print(f"  BUILD_DATE: {date}")
        print(f"  STATUS: {status}")
        print(f"  BRANCH: {branch}")
        return True
    
    # Write back JSON with proper formatting
    try:
        with open(project_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')  # Add trailing newline
        print(f"✓ Updated {project_file}:")
        print(f"  VERSION: {revision}")
        print(f"  BUILD_DATE: {date}")
        print(f"  STATUS: {status}")
        print(f"  BRANCH: {branch}")
        return True
    except Exception as e:
        print(f"Error writing {project_file}: {e}", file=sys.stderr)
        return False


def update_kicad_project_sexpr(project_file, dry_run=False):
    """Update text variables in S-expression format KiCad project file (KiCad 6-8)."""
    
    repo_dir = project_file.parent
    
    # Get git information
    revision, date, branch = get_git_info(repo_dir)
    if revision is None:
        return False
    
    # Read the project file
    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {project_file}: {e}", file=sys.stderr)
        return False
    
    original_content = content
    
    # Check if text_variables section exists
    text_vars_match = re.search(r'\(text_variables\s*\n(.*?)\n\s*\)', content, re.DOTALL)
    
    if text_vars_match:
        # Update existing section
        text_vars_content = text_vars_match.group(1)
        
        if re.search(r'\(VERSION\s+"[^"]*"\)', text_vars_content):
            text_vars_content = re.sub(
                r'\(VERSION\s+"[^"]*"\)',
                f'(VERSION "{revision}")',
                text_vars_content
            )
        else:
            text_vars_content += f'\n    (VERSION "{revision}")'
        
        if re.search(r'\(BUILD_DATE\s+"[^"]*"\)', text_vars_content):
            text_vars_content = re.sub(
                r'\(BUILD_DATE\s+"[^"]*"\)',
                f'(BUILD_DATE "{date}")',
                text_vars_content
            )
        else:
            text_vars_content += f'\n    (BUILD_DATE "{date}")'
        
        new_text_vars = f'(text_variables\n{text_vars_content}\n  )'
        content = content[:text_vars_match.start()] + new_text_vars + content[text_vars_match.end():]
    else:
        # Create new section
        text_vars_section = f'''  (text_variables
    (VERSION "{revision}")
    (BUILD_DATE "{date}")
  )
'''
        match = re.search(r'(\(kicad_pro.*?\n)', content)
        if match:
            content = content[:match.end()] + text_vars_section + content[match.end():]
    
    if content == original_content:
        print(f"No changes needed for {project_file}")
        return True
    
    if dry_run:
        print(f"Would update {project_file}:")
        print(f"  VERSION: {revision}")
        print(f"  BUILD_DATE: {date}")
        return True
    
    try:
        with open(project_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Updated {project_file}:")
        print(f"  VERSION: {revision}")
        print(f"  BUILD_DATE: {date}")
        return True
    except Exception as e:
        print(f"Error writing {project_file}: {e}", file=sys.stderr)
        return False

def diagnose_project(project_file):
    """Show text variables in the project file."""
    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {project_file}: {e}", file=sys.stderr)
        return
    
    print(f"\n=== Analyzing {project_file} ===")
    
    # Detect format
    is_json = content.strip().startswith('{')
    print(f"Format: {'JSON (KiCad 9+)' if is_json else 'S-expression (KiCad 6-8)'}")
    
    if is_json:
        try:
            data = json.loads(content)
            if 'text_variables' in data:
                print("\n✓ Text variables found:")
                for key, value in data['text_variables'].items():
                    print(f"  ${{{key}}}: \"{value}\"")
            else:
                print("\n⚠ No text_variables in JSON")
        except json.JSONDecodeError as e:
            print(f"\n⚠ Invalid JSON: {e}")
    else:
        text_vars = re.search(r'\(text_variables.*?\n\s*\)', content, re.DOTALL)
        if text_vars:
            print("\n✓ Text variables found:")
            print(text_vars.group(0))
        else:
            print("\n⚠ No text_variables section found")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Auto-update version variables in KiCad projects from git',
        epilog='''
Examples:
  # Update project and all schematics
  %(prog)s myproject.kicad_pro
  
  # Preview changes
  %(prog)s --dry-run myproject.kicad_pro
  
  # Check what's currently in the project
  %(prog)s --diagnose myproject.kicad_pro

In your PCB silkscreen, add text: ${VERSION}
In your schematics, the title block will automatically show the version.
        '''
    )
    parser.add_argument(
        'project',
        type=Path,
        help='KiCad project file (.kicad_pro)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files'
    )
    parser.add_argument(
        '--project-only',
        action='store_true',
        help='Only update project file, not schematics'
    )
    parser.add_argument(
        '--diagnose',
        action='store_true',
        help='Show what variables are currently in the project file'
    )
    
    args = parser.parse_args()
    
    if not args.project.exists():
        print(f"Error: {args.project} does not exist", file=sys.stderr)
        return 1
    
    if args.project.suffix != '.kicad_pro':
        print(f"Error: {args.project} is not a .kicad_pro file", file=sys.stderr)
        return 1
    
    # Diagnose mode
    if args.diagnose:
        diagnose_project(args.project)
        return 0
    
    # Detect format and update accordingly
    try:
        with open(args.project, 'r', encoding='utf-8') as f:
            content = f.read()
        is_json = content.strip().startswith('{')
    except Exception as e:
        print(f"Error reading {args.project}: {e}", file=sys.stderr)
        return 1
    
    # Update the project file
    if is_json:
        if not update_kicad_project_json(args.project, args.dry_run):
            return 1
    else:
        if not update_kicad_project_sexpr(args.project, args.dry_run):
            return 1
    
    if args.project_only:
        return 0
    
    # Find and update all schematics
    project_dir = args.project.parent
    
    if not args.dry_run:
        print("\n" + "="*60)
        print("✓ Done! Version variables are now set up.")
        print("\nTo use in your PCB silkscreen:")
        print("  1. Add a text item on your silkscreen layer")
        print("  2. Enter: ${VERSION}")
        print("  3. KiCad will automatically substitute the version")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
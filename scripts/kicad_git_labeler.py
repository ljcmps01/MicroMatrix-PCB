#!/usr/bin/env python3
"""
KiCad Schematic Git Auto-labeler
Automatically updates Rev and Date fields in KiCad schematics based on git info
"""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_git_info(file_path):
    """Get git revision and date information for a file."""
    try:
        repo_dir = file_path.parent
        
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
        
        # Add branch name if not on master/main
        if branch not in ['master', 'main']:
            revision += f"-{branch}"
        
        # Get the commit date of the file
        commit_date = subprocess.check_output(
            ['git', 'log', '-1', '--format=%ci', '--', file_path.name],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        # If file has no commits yet, use current date
        if not commit_date:
            commit_date = datetime.now().strftime('%Y-%m-%d')
        else:
            # Extract just the date part
            commit_date = commit_date.split()[0]
        
        # Check if there are uncommitted changes
        status = subprocess.check_output(
            ['git', 'status', '--porcelain', '--', file_path.name],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        if status:
            revision += '-dirty'
            commit_date = datetime.now().strftime('%Y-%m-%d')
        
        return revision, commit_date
        
    except subprocess.CalledProcessError as e:
        print(f"Error: {file_path} is not in a git repository or git command failed", file=sys.stderr)
        return None, None


def update_kicad_schematic(file_path, dry_run=False):
    """Update Rev and Date fields in KiCad schematic file."""
    
    # Get git information
    rev, date = get_git_info(file_path)
    if rev is None:
        return False
    
    # Read the schematic file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return False
    
    original_content = content
    
    # Update title_block fields for KiCad 6/7/8/9 format
    # These fields are inside (title_block ...) and look like:
    # (rev "value") or (date "value")
    
    # Update revision field
    if re.search(r'\(title_block.*?\(rev\s+"[^"]*"\)', content, re.DOTALL):
        # Field exists, update it
        content = re.sub(
            r'(\(title_block.*?)(\(rev\s+)"[^"]*"(\))',
            rf'\1\2"{rev}"\3',
            content,
            flags=re.DOTALL
        )
    else:
        # Field doesn't exist, add it after title if present
        content = re.sub(
            r'(\(title_block\s+\(title\s+"[^"]*"\))',
            rf'\1\n\t\t(rev "{rev}")',
            content
        )
    
    # Update date field
    if re.search(r'\(title_block.*?\(date\s+"[^"]*"\)', content, re.DOTALL):
        # Field exists, update it
        content = re.sub(
            r'(\(title_block.*?)(\(date\s+)"[^"]*"(\))',
            rf'\1\2"{date}"\3',
            content,
            flags=re.DOTALL
        )
    else:
        # Field doesn't exist, add it after rev
        content = re.sub(
            r'(\(title_block.*?\(rev\s+"[^"]*"\))',
            rf'\1\n\t\t(date "{date}")',
            content,
            flags=re.DOTALL
        )
    
    # Check if anything changed
    if content == original_content:
        print(f"No changes needed for {file_path}")
        return True
    
    if dry_run:
        print(f"Would update {file_path}:")
        print(f"  Revision: {rev}")
        print(f"  Date: {date}")
        return True
    
    # Write the updated content
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Updated {file_path}:")
        print(f"  Revision: {rev}")
        print(f"  Date: {date}")
        return True
    except Exception as e:
        print(f"Error writing {file_path}: {e}", file=sys.stderr)
        return False


def diagnose_schematic(file_path):
    """Show title block fields found in the schematic."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return
    
    print(f"\n=== Analyzing {file_path} ===")
    
    # Find title_block section
    title_block = re.search(r'\(title_block(.*?)\n\t\)', content, re.DOTALL)
    if title_block:
        print("\nTitle block contents:")
        print(f"(title_block{title_block.group(1)}\n\t)")
        
        # Parse individual fields
        fields = re.findall(r'\((\w+)\s+"([^"]*)"\)', title_block.group(0))
        print("\nParsed fields:")
        for field_name, field_value in fields:
            print(f"  {field_name}: \"{field_value}\"")
    else:
        print("\nNo title_block section found")
    
    # Find all property fields (for completeness)
    properties = re.findall(r'\(property "([^"]+)" "([^"]*)"', content)
    if properties:
        print("\nOther properties found:")
        for name, value in properties[:5]:  # Show first 5
            print(f'  "{name}": "{value}"')


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Auto-update Rev and Date fields in KiCad schematics from git'
    )
    parser.add_argument(
        'files',
        nargs='+',
        type=Path,
        help='KiCad schematic files (.kicad_sch or .sch)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files'
    )
    parser.add_argument(
        '--diagnose',
        action='store_true',
        help='Show what fields are present in the schematic'
    )
    
    args = parser.parse_args()
    
    if args.diagnose:
        for file_path in args.files:
            if file_path.exists():
                diagnose_schematic(file_path)
        return 0
    
    success = True
    for file_path in args.files:
        if not file_path.exists():
            print(f"Error: {file_path} does not exist", file=sys.stderr)
            success = False
            continue
        
        if not file_path.suffix in ['.kicad_sch', '.sch']:
            print(f"Warning: {file_path} may not be a KiCad schematic", file=sys.stderr)
        
        if not update_kicad_schematic(file_path, args.dry_run):
            success = False
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
import argparse
import json
from pathlib import Path
import re
import subprocess


def run(arguments):
    return subprocess.run(['gh', *arguments], capture_output=True, text=True, timeout=30, check=True).stdout


def marked_body(body):
    text = body.rstrip()
    if not text:
        raise ValueError('reply body is empty')
    return text if text.endswith('From Codex 🤖') else text + '\n\nFrom Codex 🤖'


def reply(repository, number, expected_login, body, inline_comment=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or number <= 0:
        raise ValueError('valid repository and PR number required')
    content = marked_body(body)
    run(['auth', 'status'])
    pr = json.loads(run(['api', f'repos/{repository}/pulls/{number}']))
    if pr['user']['login'].casefold() != expected_login.casefold():
        raise PermissionError('expected writer must be the fixed PR author')
    if inline_comment is not None:
        if inline_comment <= 0:
            raise ValueError('inline comment ID must be positive')
        comment = json.loads(run(['api', f'repos/{repository}/pulls/comments/{inline_comment}']))
        if comment.get('pull_request_url') != pr['url']:
            raise ValueError('inline comment belongs to another PR')
    if run(['api', f'repos/{repository}', '--jq', '.permissions.push']).strip() != 'true':
        raise PermissionError('push permission is required before GitHub write')
    actual = run(['api', 'user', '--jq', '.login']).strip()
    if actual.casefold() != expected_login.casefold():
        raise PermissionError('GitHub API identity does not match expected writer')
    endpoint = f'repos/{repository}/pulls/{number}/comments/{inline_comment}/replies' if inline_comment is not None else f'repos/{repository}/issues/{number}/comments'
    result = subprocess.run(['gh', 'api', '--method', 'POST', endpoint, '--input', '-'], input=json.dumps({'body': content}), capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)['html_url']


def main():
    parser = argparse.ArgumentParser(description='Publish an explicitly authorized PR reply with an Agent marker')
    parser.add_argument('repository')
    parser.add_argument('number', type=int)
    parser.add_argument('--expected-login', required=True)
    parser.add_argument('--body-file', required=True, type=Path)
    parser.add_argument('--inline-comment', type=int)
    args = parser.parse_args()
    print(reply(args.repository, args.number, args.expected_login, args.body_file.read_text(), args.inline_comment))


if __name__ == '__main__':
    main()

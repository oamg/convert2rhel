<!-- Write a description of what the PR solves and how -->

<!-- Link to relevant Jira issue, add multiple if necessary -->

Jira Issues: [RHELC-](https://issues.redhat.com/browse/RHELC-)

Checklist

- [ ] PR has been tested manually in a VM (either author or reviewer)
- [ ] Jira issue has been made public if possible
- [ ] `[RHELC-]` is part of the PR title <!-- For a proper sync with Jira -->
- [ ] GitHub label has been added to help with Release notes <!-- enhancement, bug-fix, no-changelog, security-hardening, breaking-change -->
- [ ] PR title explains the change from the user's point of view

- [ ] Code and tests are documented properly
- [ ] The commits are squashed to as few commits as possible (without losing data) <!-- The commits can be squashed to 1 commit, but then we might lose data regarding moving something to a new file and then refactoring for example. Hence squash without losing data -->
- [ ] When merged: Jira issue has been updated to `Release Pending` if relevant

#!/bin/bash

set -e

source_version_value() {
  if [ ! -z "$BUILD_SOURCEBRANCH" ]; then
    BRANCH_NAME="${BUILD_SOURCEBRANCH}"
    BRANCH_NAME=${BRANCH_NAME##"refs/tags/"}
    BRANCH_NAME=${BRANCH_NAME##"refs/heads/"}

  else
    set +e
    BRANCH_NAME=$( git rev-parse --symbolic-full-name --abbrev-ref HEAD 2>/dev/null )
    set -e
  fi

  # Switch to Build.BuildNumber if BRANCH_NAME not a valid tag
  if [[ ! "$BRANCH_NAME" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-z]+\.[0-9]+)?$ ]]; then

    # Use Build.BuildNumber if present
    if [ ! -z "$BUILD_BUILDNUMBER" ]; then
      BRANCH_NAME="$BUILD_BUILDNUMBER"
    else
      BRANCH_NAME="localbuild"
    fi
  fi

  # Check branch name value exists and is valid
  if [ -z "$BRANCH_NAME" ] || [ "$BRANCH_NAME" == "HEAD" ]; then
    echo "error: git project not detected, or not initalised properly"
    echo "expecting valid tag/branch name (value was either HEAD or not present)."
    exit 1
  fi

  # Apply name fix
  BRANCH_NAME=$( echo $BRANCH_NAME | tr '/' '-' )

  # Strip 'version-*' substring if present
  BRANCH_NAME=${BRANCH_NAME##"version-"}

  # Check for 'v*.*.*' tag format
  if [[ $BRANCH_NAME =~ ^v[0-9]+.[0-9]+.[0-9]+ ]]; then
    BRANCH_NAME=${BRANCH_NAME##"v"}
  fi

  # Display version
  echo $BRANCH_NAME
}

source_version_value

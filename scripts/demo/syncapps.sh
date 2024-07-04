#!/bin/bash

oc ns openshift-gitops
argocd login cd.argoproj.io --core
argocd app sync $1
oc ns video
oc get po

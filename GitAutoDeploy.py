#!/usr/bin/env python

import json, urlparse, sys, os
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from subprocess import call, Popen
from threading import Thread

class GitAutoDeploy(BaseHTTPRequestHandler):

    SCRIPT_PATH = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    CONFIG_FILEPATH = os.path.join(SCRIPT_PATH, 'GitAutoDeploy.conf.json')
    NEWRELIC_DEPLOY = ('curl;-H;"x-api-key:%s";'
                       '-d;"deployment[application_id]=%d";'
                       '-d;"deployment[description]=%s";'
                       '-d;"deployment[revision]=%s";'
                       '-d;"deployment[user]=Github Auto Deploy";'
                       'https://api.newrelic.com/deployments.xml')
    config = None
    quiet = False
    daemon = False

    @classmethod
    def getConfig(myClass):
        if(myClass.config == None):
            try:
                configString = open(myClass.CONFIG_FILEPATH).read()
            except:
                sys.exit('Could not load ' + myClass.CONFIG_FILEPATH + ' file')

            try:
                myClass.config = json.loads(configString)
            except:
                sys.exit(myClass.CONFIG_FILEPATH + ' file is not valid json')

            for repository in myClass.config['repositories']:
                if(not os.path.isdir(repository['path'])):
                    sys.exit('Directory ' + repository['path'] + ' not found')
                if(not os.path.isdir(repository['path'] + '/.git')):
                    sys.exit('Directory ' + repository['path'] + ' is not a Git repository')

        return myClass.config

    def do_POST(self):
        url_refs = self.parseRequest()
        matchingPaths = []

        for url, ref, sha in url_refs:
            paths = self.getMatchingPaths(url, ref, sha)

        for path in paths:
            matchingPaths.append(path)

        self.respond(matchingPaths)

        for path in matchingPaths:
            self.pull(path)
            self.deploy(path)

    def parseRequest(self):
        length = int(self.headers.getheader('content-length'))
        body = self.rfile.read(length)
        post = urlparse.parse_qs(body)
        items = []

        for itemString in post['payload']:
            item = json.loads(itemString)
            items.append((item['repository']['url'], item['ref'], item['after']))

        return items

    def getMatchingPaths(self, repoUrl, ref, sha):
        res = []
        config = self.getConfig()

        for repository in config['repositories']:
            if(repository['url'] == repoUrl and repository.get('ref', '') in ('', ref)):
                res.append((repository['path'], repository.get('ref',''), sha))

        return res

    def respond(self,paths):
        self.send_response(200, paths)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

        if (len(paths) == 0):
            self.wfile.write('No repositorys need to be redeployed.')
        else:
            for path in paths:
                self.wfile.write('\"' + path[0] + '\" Will be redeployed.')


    def pull(self, path):
        if(not self.quiet):
            print "\nPost push request received"
            print "Updating %s refspec %s" % (path[0], path[1])
        call(['cd "' + path[0] + '" && git pull origin "' + path[1] +'"'], shell=True)

    def deploy(self, path):
        config = self.getConfig()
        for repository in config['repositories']:
            if(repository['path'] == path[0]):
                if 'deploy' in repository:
                    if(not self.quiet):
                         print 'Executing deploy command'
                    call('cd '+path[0]+' && '+repository['deploy'], shell=True)

                if 'newrelic' in repository:
                    if(not self.quiet):
                         print 'Reporting deploy to Newrelic'
                    try:
                        command = self.NEWRELIC_DEPLOY % \
                            (repository['newrelic']['api'],
                             int(repository['newrelic']['app_id']),
                             repository['newrelic']['description'],
                             path[2])

                        call(command.split(';'), shell=True)
                    except OSError as e:
                        if(e):
                            print >> sys.stderr, e

                break

def main():
    try:
        server = None
        for arg in sys.argv:
            if(arg == '-d' or arg == '--daemon-mode'):
                GitAutoDeploy.daemon = True
                GitAutoDeploy.quiet = True
            if(arg == '-q' or arg == '--quiet'):
                GitAutoDeploy.quiet = True

        if(GitAutoDeploy.daemon):
            pid = os.fork()
            if(pid != 0):
                sys.exit()
            os.setsid()

        if(not GitAutoDeploy.quiet):
            print 'Github Autodeploy Service v 0.2 started'
        else:
            print 'Github Autodeploy Service v 0.2 started in daemon mode'

        server = HTTPServer(('', GitAutoDeploy.getConfig()['port']), GitAutoDeploy)
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit) as e:
        if(e): # wtf, why is this creating a new line?
            print >> sys.stderr, e

        if(not server is None):
            server.socket.close()

        if(not GitAutoDeploy.quiet):
            print 'Goodbye'

if __name__ == '__main__':
     main()

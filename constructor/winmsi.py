# (c) 2016 Continuum Analytics, Inc. / http://continuum.io
# All Rights Reserved
#
# constructor is distributed under the terms of the BSD 3-clause license.
# Consult LICENSE.txt or http://opensource.org/licenses/BSD-3-Clause.

from __future__ import print_function, division, absolute_import

import os
import sys
import shutil
import tempfile
from itertools import chain
from six.moves import zip_longest
from os.path import abspath, dirname, isfile, join
from subprocess import check_call, check_output
import uuid
from xml.sax.saxutils import escape as escape_xml

from constructor.construct import ns_platform
from constructor.install import name_dist
from constructor.utils import make_VIProductVersion, preprocess, fill_template
from constructor.imaging import write_images
import constructor.preconda as preconda


THIS_DIR = dirname(__file__)
WIX_DIR = join(THIS_DIR, 'wix')
CANDLE_EXE = join(sys.prefix, 'wix', 'candle.exe')
LIGHT_EXE = join(sys.prefix, 'wix', 'light.exe')

EXTENSIONS = ['WixUIExtension']

# WARNING: DO NOT MODIFY THIS UUID, AS IT WILL BREAK 
# BACKWARDS COMPATIBILITY OF ALL GENERATED INSTALLERS
# IF YOU DO!
CONSTRUCTOR_UUID_NAMESPACE = uuid.UUID('{00dde158-c9df-4fb2-b4d0-b363906936ac}')


def namespace_uuid(name):
    return str(uuid.uuid5(CONSTRUCTOR_UUID_NAMESPACE, name)).upper()

def random_uuid():
    return str(uuid.uuid4())

def escape_id(id):
    return id.replace('-', '')

def read_wxs_tmpl():
    path = join(WIX_DIR, 'template.wxs')
    print('Reading: %s' % path)
    with open(path) as fi:
        return fi.read()


def find_vs_runtimes(dists, py_version):
    vs_map = {'2.7': 'vs2008_runtime',
              '3.4': 'vs2010_runtime',
              '3.5': 'vs2015_runtime'}
    vs_runtime = vs_map.get(py_version[:3])
    return [dist for dist in dists
            if name_dist(dist) in (vs_runtime, 'msvc_runtime')]


def pkg2component(download_dir, dists, py_version):
    vs_dists = find_vs_runtimes(dists, py_version)
    print("MSVC runtimes found: %s" % vs_dists)
    if len(vs_dists) != 1:
        sys.exit("Error: number of MSVC runtimes found: %d" % len(vs_dists))

    for i, fn in enumerate(vs_dists + dists):
        name, version, unused_build = fn.rsplit('-', 2)
        id = escape_xml(escape_id(name))
        source_fn = escape_xml(join(download_dir, fn))
        extracted_folder = escape_xml(fn.replace('.tar.bz2', ''))
        assert len(extracted_folder) > 0
        if i == 0: # MSVC runtimes
            assert 'runtime' in fn
            id = 'MSVC'
        elif i == 1: # Python
            assert fn.startswith('python-')
            id = 'Python'
        elif fn == vs_dists[0]:
            continue
        yield "<Component Id='%s' Guid='*'>" % id
        yield "  <File Id='%sARCHIVE' Name='%s' Source='%s' KeyPath='yes' />" % (id, escape_xml(name), source_fn)
        yield "</Component>"
        # Components to remove extracted directory when uninstalling
        yield "<Directory Id='%sDIR' Name='%s' >" % (id, extracted_folder)
        yield "  <Component Id='%sFOLDER' Guid='%s'>" % (id, namespace_uuid(name))
        yield "    <RemoveFile Id='%sPackageFiles' On='uninstall' Name='*' />" % id
        yield "    <RemoveFolder Id='%sFILES' On='uninstall' />" % id
        yield "  </Component>"
        yield "</Directory>"


def pkg2component_refs(dists, py_version):
    vs_dists = find_vs_runtimes(dists, py_version)
    print("MSVC runtimes found: %s" % vs_dists)
    if len(vs_dists) != 1:
        sys.exit("Error: number of MSVC runtimes found: %d" % len(vs_dists))

    for i, fn in enumerate(vs_dists + dists):
        name, version, unused_build = fn.rsplit('-', 2)
        if i < 2: # MSVC runtimes or Python
            continue  # Included manually in template
        elif fn == vs_dists[0]:
            continue
        else:
            yield "<ComponentRef Id='%s' />" % escape_id(name)
            yield "<ComponentRef Id='%sFOLDER' />" % escape_id(name)


def properties(info, dir_path):
    dists = info['_dists']
    py_name, py_version, unused_build = dists[0].rsplit('-', 2)
    properties = dict(
        WixDir=WIX_DIR,
        PythonVersion=py_version[:3],
        PythonVersionJustDigits=''.join(py_version.split('.')),
        ResourcePath=dir_path,
        Name=info['name'],
        EnvGUID=random_uuid(),
    )
    for key, fn in [('HeaderImage', 'header.bmp'),
                    ('WelcomeImage', 'welcome.bmp'),
                    ('IconFile', 'icon.ico'),
                    ('InstallPy', '.install.py'),
                    ('UrlsFile', 'urls'),
                    ('UrlsTxtFile', 'urls.txt'),
                    ('PostInstall', 'post_install.bat')]:
        properties[key] = fn
    
    for key, value in properties.items():
        value = escape_xml(value)
        yield "<?define %s='%s'?>" % (key, value)


def make_wxs(info, dir_path):
    "Creates the tmp/main.wxs from the template file"
    name = info['name']
    major_version = info['version'].split('.', 1)[0]
    # All updates are "major" updates:
    product_uuid = str(uuid.uuid4())
    # Note: Add a token to name from our side if we/conda ever 
    # break major update capability:
    upgrade_uuid = namespace_uuid(name + major_version)
    download_dir = info['_download_dir']
    dists = info['_dists']
    py_name, py_version, unused_build = dists[0].rsplit('-', 2)
    assert py_name == 'python'
    arch = int(info['_platform'].split('-')[1])
    web_cmd = WEB_ENVIRONMENT_CMD if 'web_environment' in info else ''

    # these appear as __<key>__ in the template, and get escaped
    replace = {
        'NAME': name,
        'VERSION': info['version'],
        'COMPANY': info.get('company', 'Unknown, Inc.'),
        'PRODUCT_GUID': product_uuid,
        'UPGRADE_GUID': upgrade_uuid,
        'LICENSEFILE': abspath(info.get('license_file',
                               join(WIX_DIR, 'placeholder_license.txt'))),
    }
    for key in replace:
        replace[key] = escape_xml(replace[key])

    data = read_wxs_tmpl()
    data = preprocess(data, ns_platform(info['_platform']))
    data = fill_template(data, replace)

    props = properties(info, dir_path)
    components = pkg2component(download_dir, dists, py_version)
    comp_refs = pkg2component_refs(dists, py_version)
    # these are unescaped (and unquoted)
    for key, value in [
        ('@PROPERTIES@', '\n  '.join(props)),
        ('@PKG_COMPONENTS@', '\n          '.join(components)),
        ('@PKG_COMPONENTS_REFS@', '\n        '.join(comp_refs)),
        ('@WEB_ENVIRONMENT@', '\n    '.join(web_cmd.splitlines())),
        ('@MENU_PKGS@', ' '.join(info.get('menu_packages', []))),
        ]:
        data = data.replace(key, value)

    wxs_path = join(dir_path, 'main.wxs')
    with open(wxs_path, 'w') as fo:
        fo.write(data)

    print('Created %s file' % wxs_path)
    return wxs_path


def verify_wix_install():
    print("Checking for '%s'" % CANDLE_EXE)
    if not isfile(CANDLE_EXE):
        sys.exit("""
Error: no file %s
    please make sure Wix is installed:
    > conda install -n root wix
""" % CANDLE_EXE)
    out = check_output([CANDLE_EXE, '-help'])
    out = out.decode('utf-8').splitlines()[0].strip()
    print(out)
    print("Checking for '%s'" % LIGHT_EXE)
    if not isfile(LIGHT_EXE):
        sys.exit("""
Error: no file %s
    please make sure Wix is installed:
    > conda install -n root wix
""" % LIGHT_EXE)
    out = check_output([LIGHT_EXE, '-help'])
    out = out.decode('utf-8').splitlines()[0].strip()
    print(out)


def create(info):
    verify_wix_install()
    # tmp_dir = tempfile.mkdtemp()
    tmp_dir = 'c:\\github\\ctorout\\build\\'
    preconda.write_files(info, tmp_dir)
    if 'pre_install' in info:
        sys.exit("Error: Cannot run pre install on Windows, sorry.\n")

    post_dst = join(tmp_dir, 'post_install.bat')
    try:
        shutil.copy(info['post_install'], post_dst)
    except KeyError:
        with open(post_dst, 'w') as fo:
            fo.write(":: this is an empty post install .bat script\n")

    if 'web_environment' in info:
        env_dst = join(tmp_dir, 'web_environment.yml')
        shutil.copy(info['web_environment'], env_dst)

    write_images(info, tmp_dir)

    wxs = make_wxs(info, tmp_dir)
    args = [CANDLE_EXE, '-out', tmp_dir, wxs]
    print('Calling: %s' % args)
    check_call(args)

    wixobj = os.path.splitext(wxs)[0] + '.wixobj'
    # ['extA', 'extB'] -> ['-ext', 'extA', '-ext', 'extB']
    ext_args = list(chain(*zip_longest([], EXTENSIONS, fillvalue=['-ext'])))
    args = [LIGHT_EXE] + ext_args + [wixobj]
    print('Calling: %s' % args)
    check_call(args)
    #shutil.rmtree(tmp_dir)


if __name__ == '__main__':
    make_nsi({'name': 'Maxi', 'version': '1.2',
              '_platform': 'win-64',
              '_outpath': 'dummy.exe',
              '_download_dir': 'dummy',
              '_dists': ['python-2.7.9-0.tar.bz2',
                         'vs2008_runtime-1.0-1.tar.bz2']},
             '.')

# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import zipfile, traceback, argparse, collections

from . import parsedex
from .jvm import writeclass
from .mutf8 import decode
from .jvm.optimization import options

def read(fname, mode='rb'):
    with open(fname, mode) as f:
        return f.read()

def translate(data, opts, classes=None, errors=None):
    dex = parsedex.DexFile(data)
    classes = collections.OrderedDict() if classes is None else classes
    errors = collections.OrderedDict() if errors is None else errors

    for cls in dex.classes:
        unicode_name = decode(cls.name) + '.class'
        if unicode_name in classes or unicode_name in errors:
            print('Warning, duplicate class name', unicode_name)
            continue

        try:
            class_data = writeclass.toClassFile(cls, opts)
            classes[unicode_name] = class_data
        except Exception:
            errors[unicode_name] = traceback.format_exc()

        if not (len(classes) + len(errors)) % 1000:
            print(len(classes) + len(errors), 'classes processed')
    return classes, errors

def writeToJar(fname, classes):
    with zipfile.ZipFile(fname, 'w') as out:
        for unicode_name, data in classes.items():
            # Don't bother compressing small files
            compress_type = zipfile.ZIP_DEFLATED if len(data) > 10000 else zipfile.ZIP_STORED
            out.writestr(zipfile.ZipInfo(unicode_name), data, compress_type=compress_type)

def main():
    parser = argparse.ArgumentParser(prog='enjarify', description='Translates Dalvik bytecode (.dex or .apk) to Java bytecode (.jar)')
    parser.add_argument('inputfile')
    parser.add_argument('-o', '--output', help='Output .jar file. Default is [input-filename]-enjarify.jar.')
    parser.add_argument('-f', '--force', action='store_true', help='Force overwrite. If output file already exists, this option is required to overwrite.')
    parser.add_argument('--fast', action='store_true', help='Speed up translation at the expense of generated bytecode being less readable.')
    args = parser.parse_args()

    dexs = []
    if args.inputfile.endswith('apk'):
        with zipfile.ZipFile(args.inputfile, 'r') as z:
            for name in z.namelist():
                if name.startswith('classes') and name.endswith('.dex'):
                    dexs.append(z.read(name))
    else:
        dexs.append(read(args.inputfile))

    # Exclusive mode requires 3.3+, so provide helpful error in this case
    if not args.force:
        try:
            FileExistsError
        except NameError:
            print('Overwrite protection requires Python 3.3+. Either pass -f or --force, or upgrade to a more recent version of Python. If you are using Pypy3 2.4, you need to switch to a nightly build or build from source. Or just pass -f.')
            return

    # Might as well open the output file early so we can detect existing file error
    # before going to the trouble of translating everything
    outname = args.output or args.inputfile.rpartition('/')[-1].rpartition('.')[0] + '-enjarify.jar'
    try:
        outfile = open(outname, mode=('wb' if args.force else 'xb'))
    except FileExistsError:
        print('Error, output file already exists and --force was not specified.')
        print('To overwrite the output file, pass -f or --force.')
        return

    opts = options.NONE if args.fast else options.PRETTY
    classes = collections.OrderedDict()
    errors = collections.OrderedDict()
    for data in dexs:
        translate(data, opts=opts, classes=classes, errors=errors)
    writeToJar(outfile, classes)
    outfile.close()
    print('Output written to', outname)

    for name, error in sorted(errors.items()):
        print(name, error)
    print('{} classes translated successfully, {} classes had errors'.format(len(classes), len(errors)))

if __name__ == "__main__":
    main()

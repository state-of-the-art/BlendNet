#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Blend File

Description: Useful functions to get info about the loaded blend file
'''

import os
import bpy
import glob

try:
    from . import utils
except ImportError:
    # In case loaded as a regular script
    import utils

def getDependencies(project_path, cwd_path, change = False):
    '''Will return good and bad set of file dependencies'''
    # * project_path - absolute path to the project on the client system
    # * cwd_path - absolute path to the current working directory on the client system
    # * change - replace the path in blend project with the changed one
    good, bad = checkImages(project_path, cwd_path, change)

    data = checkCaches(project_path, cwd_path, change)
    good = good.union(data[0])
    bad = bad.union(data[1])

    return good, bad

def fixPath(path, project_path, cwd_path, change):
    '''Will make sure the path is properly formatted'''
    newpath = path.replace('\\', '/')
    # Make sure the blend file path is absolute for further processing
    if newpath.startswith('//') and project_path:
        # Convert the project (starts with '//') paths - they could
        # contain parent dir usage, so need to ensure it's ok
        newpath = utils.resolvePath(os.path.join(project_path, newpath[2:]))
    elif not utils.isPathAbsolute(newpath) and cwd_path:
        # Looks like relative path to the cwd - so making it
        newpath = utils.resolvePath(os.path.join(cwd_path, newpath))

    # Now the path is absolute and we can modify it to the actual path
    if newpath.startswith(project_path):
        newpath = '//' + newpath.replace(project_path, '', 1).lstrip('/')
    elif change:
        newpath = '//../ext_deps/' + newpath.replace(':', '_').lstrip('/')

    return newpath

def checkImages(project_path, cwd_path, change):
    '''Will go through images, check they are existing and return good and bad set of files'''
    good = set()
    bad = set()

    for i in bpy.data.images:
        if i.packed_file or i.source != 'FILE':
            continue

        path = fixPath(i.filepath, project_path, cwd_path, change)
        if not os.path.isfile(bpy.path.abspath(path)):
            print('ERROR: Unable to locate the image file:', path)
            bad.add(i.filepath)
            continue
        if change:
            i.filepath = path

        good.add(path)

    return good, bad

def checkCaches(project_path, cwd_path, change):
    '''Will go through caches, check they are existing and return good and bad set of files'''
    scene = bpy.context.scene

    good = set()
    bad = set()

    localdir = bpy.path.abspath('//')
    pointcache_dir = 'blendcache_' + os.path.basename(bpy.data.filepath).rsplit('.', 1)[0]
    for o in bpy.data.objects:
        if not o.visible_get():
            continue
        for mod in o.modifiers:
            pcloc = None
            ext = None

            if mod.type == 'FLUID' and mod.fluid_type == 'DOMAIN':
                # New mantaflow added in 2.82
                cachedir = fixPath(mod.domain_settings.cache_directory, project_path, cwd_path, change)
                if not os.path.isdir(bpy.path.abspath(cachedir)):
                    print('ERROR: Unable to locate the cachedir "%s" for object modifier %s --> %s' %
                            (mod.domain_settings.cache_directory, o.name, mod.name))
                    bad.add(cachedir)
                    continue

                if change:
                    mod.domain_settings.cache_directory = cachedir

                def _fmt(ext_type):
                    return {
                        'UNI': 'uni',
                        'OPENVDB': 'vdb',
                        'RAW': 'raw',
                        'OBJECT': 'obj',
                        'BOBJECT': 'bobj.gz',
                    }.get(ext_type, ext_type)

                files = []
                ds = mod.domain_settings

                # Common config
                files.append('config/config_%04d.uni' % scene.frame_current)

                # Common data
                files.append('data/vel_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))
                files.append('data/velTmp_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))

                if ds.domain_type == 'FLUID':
                    # For some reason openvdb is not saving these files
                    if ds.cache_data_format != 'OPENVDB':
                        # Particle Data
                        files.append('data/pp_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))
                        # Particle Velocity
                        files.append('data/pVel_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))
                elif ds.domain_type == 'GAS':
                    files.append('data/density_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))
                    files.append('data/shadow_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))
                    files.append('data/heat_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))
                    #if fire:
                    #    files.append('data/flame_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))

                if ds.use_spray_particles or ds.use_foam_particles or ds.use_bubble_particles:
                    # If Spray is set
                    files.append('particles/ppSnd_%04d.%s' % (scene.frame_current, _fmt(ds.cache_particle_format)))
                    files.append('particles/pVelSnd_%04d.%s' % (scene.frame_current, _fmt(ds.cache_particle_format)))
                    files.append('particles/pLifeSnd_%04d.%s' % (scene.frame_current, _fmt(ds.cache_particle_format)))

                if ds.use_mesh:
                    # If Mesh is set
                    files.append('mesh/lMesh_%04d.%s' % (scene.frame_current, _fmt(ds.cache_mesh_format)))
                    # For some reason openvdb is not saving this file
                    if ds.use_speed_vectors and ds.cache_data_format != 'OPENVDB':
                        files.append('mesh/lVelMesh_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))

                if ds.use_guide:
                    # If Guides is set
                    files.append('guiding/guidevel_%04d.%s' % (scene.frame_current, _fmt(ds.cache_data_format)))

                if ds.use_noise:
                    # If Noise is set
                    files.append('noise/density_noise_%04d.%s' % (scene.frame_current, _fmt(ds.cache_noise_format)))
                    #if fire:
                    #   files.append('noise/flame_noise_%04d.%s' % (scene.frame_current, _fmt(ds.cache_noise_format)))

                print('DEBUG: Expecting files:', files)
                for f in files:
                    cpath = os.path.join(cachedir, f)
                    if not os.path.isfile(bpy.path.abspath(cpath)):
                        print('ERROR: Unable to locate fluid cache file '
                              '"%s" for object modifier %s --> %s' % (cpath, o.name, mod.name))
                        bad.add(cpath)
                        continue
                    good.add(cpath)

                # Some settings are attached to other objects (like flow for fire/smoke)
                # so it's hard to determine right now, let's use just glob to find related
                files_additional = glob.glob(os.path.join(cachedir, '**/*_%04d.*' % (scene.frame_current,)))
                for cpath in files_additional:
                    cpath = fixPath(cpath, project_path, cwd_path, change)
                    if cpath not in good:
                        print('INFO: Found an additional fluid cache file:', cpath)
                        good.add(cpath)

                continue

            elif mod.type == 'FLUID_SIMULATION' and mod.settings.type in ('DOMAIN', 'PARTICLE'):
                # Deprecated in blender >= 2.82
                cachedir = fixPath(mod.settings.filepath, project_path, cwd_path, change)
                if not os.path.isdir(bpy.path.abspath(cachedir)):
                    print('ERROR: Unable to find the cachedir "%s" for object modifier %s --> %s' %
                            (mod.settings.filepath, o.name, mod.name))
                    bad.add(mod.settings.filepath)
                    continue

                if change:
                    mod.settings.filepath = cachedir

                files = None
                if mod.settings.type == 'DOMAIN':
                    files = [
                        'fluidsurface_preview_%04d.bobj.gz' % scene.frame_current,
                        'fluidsurface_final_%04d.bobj.gz' % scene.frame_current
                    ]
                    if mod.settings.use_speed_vectors:
                        files.append('fluidsurface_final_%04d.bvel.gz' % scene.frame_current)
                elif mod.settings.type == 'PARTICLE':
                    files = ['fluidsurface_particles_%04d.gz' % scene.frame_current]
                else:
                    continue
                for f in files:
                    cpath = os.path.join(cachedir, f)
                    if not os.path.isfile(bpy.path.abspath(cpath)):
                        print('ERROR: Unable to locate fluid sim cache file '
                              '"%s" for object modifier %s --> %s' % (cpath, o.name, mod.name))
                        bad.add(cpath)
                    else:
                        good.add(cpath)
                continue
            elif mod.type == 'SMOKE':
                # Deprecated in blender >= 2.82
                if mod.smoke_type != 'DOMAIN':
                    continue
                ext = '.vdb' if mod.domain_settings.cache_file_format == 'OPENVDB' else '.bphys'
                pclocs = [mod.domain_settings.point_cache]
            elif mod.type == 'CLOTH':
                ext = '.bphys'
                pclocs = [mod.point_cache]
            elif mod.type == 'DYNAMIC_PAINT':
                if mod.ui_type != 'CANVAS':
                    continue
                ext = '.bphys'
                pclocs = [loc.point_cache for loc in mod.canvas_settings.canvas_surfaces if loc.surface_format == 'VERTEX']
            else:
                continue

            for pcloc in pclocs:
                pc = pcloc.point_caches[pcloc.point_caches.active_index]
                index = pcloc.point_caches.active_index if pc.index < 0 else pc.index
                if not pc.use_disk_cache:
                    continue

                if scene.frame_current not in range(pc.frame_start, pc.frame_end+1, pc.frame_step):
                    continue

                fname = pc.name if pc.name else ''.join([ hex(ord(c))[2:].zfill(2) for c in o.name ])
                if not pc.use_external or index > 0:
                    fname = '%s_%06d_%02u%s' % (fname, scene.frame_current, index, ext)
                else:
                    fname = '%s_%06d%s' % (fname, scene.frame_current, ext)

                cpath = fixPath(os.path.join('//', pointcache_dir, fname), project_path, cwd_path, change)
                if not os.path.isfile(bpy.path.abspath(cpath)):
                    print('ERROR: Unable to locate pointcache file '
                          '"%s" for object modifier %s --> %s' % (cpath, o.name, mod.name))
                    bad.add(cpath)
                else:
                    good.add(cpath)

    return good, bad

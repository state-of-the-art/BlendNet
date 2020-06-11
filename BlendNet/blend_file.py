#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Blend File

Description: Useful functions to get info about the loaded blend file
'''

import os
import bpy

def getDependencies():
    '''Will return good and bad set of file dependencies'''
    good, bad = getImages()

    data = getCaches()
    good = good.union(data[0])
    bad = bad.union(data[1])

    return good, bad

def getImages():
    '''Will go through images, check they are existing and return good and bad set of files'''
    good = set()
    bad = set()

    localdir = bpy.path.abspath('//')
    for i in bpy.data.images:
        if i.packed_file or i.source != 'FILE':
            continue

        path = os.path.realpath(bpy.path.abspath(i.filepath)).replace(localdir, '', 1)

        if not os.path.isfile(os.path.join(localdir, path)):
            print('ERROR: Unable to find image: "%s"' % i.filepath)
            bad.add(i.filepath)
        else:
            good.add(path)
            i.filepath = '//'+path

    return good, bad

def getCaches():
    '''Will go through caches, check they are existing and return good and bad set of files'''
    scene = bpy.context.scene

    good = set()
    bad = set()

    localdir = bpy.path.abspath('//')
    pointcache_dir = 'blendcache_%s' % os.path.basename(bpy.data.filepath)[:-6]
    for o in bpy.data.objects:
        if not o.visible_get():
            continue
        for mod in o.modifiers:
            pcloc = None
            ext = None

            if mod.type == 'FLUID' and mod.fluid_type == 'DOMAIN':
                # New mantaflow added in 2.82
                cachedir = os.path.realpath(bpy.path.abspath(mod.domain_settings.cache_directory)).replace(localdir, '', 1)
                if not os.path.isdir(os.path.join(localdir, cachedir)):
                    print('ERROR: Not a relative/not existing path of the cachedir '
                          '"%s" for object modifier %s --> %s' % (mod.domain_settings.cache_directory, o.name, mod.name))
                    bad.add(mod.settings.filepath)
                    continue

                mod.domain_settings.cache_directory = '//'+cachedir

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

                for f in files:
                    cpath = os.path.join(cachedir, f)
                    if not os.path.isfile(os.path.join(localdir, cpath)):
                        print('ERROR: Unable to locate fluid cache file '
                              '"%s" for object modifier %s --> %s' % (cpath, o.name, mod.name))
                        bad.add(cpath)
                    else:
                        good.add(cpath)

                # Some settings are attached to other objects (like flow for fire/smoke)
                # so it's hard to determine right now, let's use just glob to find related
                import glob
                files_additional = glob.glob(os.path.join(localdir, cachedir, '**/*_%04d.*' % scene.frame_current), recursive=True)
                for f in files_additional:
                    cpath = f.replace(localdir, '')
                    if cpath not in files:
                        print('INFO: Found additional fluid cache file to upload: %s' % (cpath,))
                        good.add(cpath)

                continue

            elif mod.type == 'FLUID_SIMULATION' and mod.settings.type in ('DOMAIN', 'PARTICLE'):
                # Deprecated: < 2.82
                cachedir = os.path.realpath(bpy.path.abspath(mod.settings.filepath)).replace(localdir, '', 1)
                if not os.path.isdir(os.path.join(localdir, cachedir)):
                    print('ERROR: Not a relative/not existing path of the cachedir '
                          '"%s" for object modifier %s --> %s' % (mod.settings.filepath, o.name, mod.name))
                    bad.add(mod.settings.filepath)
                    continue

                mod.settings.filepath = '//'+cachedir

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
                    if not os.path.isfile(os.path.join(localdir, cpath)):
                        print('ERROR: Unable to locate fluid sim cache file '
                              '"%s" for object modifier %s --> %s' % (cpath, o.name, mod.name))
                        bad.add(cpath)
                    else:
                        good.add(cpath)
                continue
            elif mod.type == 'SMOKE':
                # Deprecated: < 2.82
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

                cpath = os.path.join(pointcache_dir, fname)
                if not os.path.isfile(os.path.join(localdir, cpath)):
                    print('ERROR: Unable to locate pointcache file '
                          '"%s" for object modifier %s --> %s' % (cpath, o.name, mod.name))
                    bad.add(cpath)
                else:
                    good.add(cpath)

    return good, bad
